"""
Ý tưởng: Dịch phụ đề SRT với bối cảnh và xưng hô tuỳ chỉnh, sau đó chuyển thành giọng nói (Edge-TTS).
Yêu cầu: 
    pip install edge-tts pydub whisper googletrans==4.0.0-rc1
    ffmpeg cần có trong PATH để pydub export/play được.
"""


import os
import re
import io
import json
import asyncio
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pydub import AudioSegment
import edge_tts
import whisper
from googletrans import Translator
import datetime
import srt

# ---------------- Config ----------------
translator = Translator()
WHISPER_MODELS = {}

LANGUAGES = {
    "Tiếng Việt": "vi",
    "English": "en",
    "日本語 (Japanese)": "ja",
    "中文 (Chinese Simplified)": "zh-cn",
    "한국어 (Korean)": "ko",
    "Français (French)": "fr",
    "Deutsch (German)": "de",
    "Español (Spanish)": "es"
}

# ---------------- Whisper utils ----------------
def get_whisper_model(size="base"):
    if size not in WHISPER_MODELS:
        WHISPER_MODELS[size] = whisper.load_model(size)
    return WHISPER_MODELS[size]

def transcribe_audio(audio_path, model_size="base"):
    model = get_whisper_model(model_size)
    result = model.transcribe(audio_path)
    return result['segments'], result.get("language", "unknown")

# ---------------- Translation & Context ----------------
def translate_text_with_context(text, dest_lang="en", context_words=None, honorific_style="modern"):
    """Dịch text, áp dụng bối cảnh và xưng hô"""
    # Thêm các từ gợi ý bối cảnh vào text
    if context_words:
        text = text + " " + " ".join(context_words)
    # Đơn giản: nếu cổ đại, thay một số đại từ/cụm từ
    if honorific_style == "ancient":
        text = text.replace("you", "ngươi").replace("I", "ta").replace("my", "của ta")
    try:
        translated = translator.translate(text, dest=dest_lang)
        return translated.text
    except Exception:
        return text

# ---------------- Edge-TTS helpers ----------------
async def _list_voices_async():
    return await edge_tts.list_voices()

def fetch_all_voices():
    try:
        voices = asyncio.run(_list_voices_async())
        voice_items = []
        for v in voices:
            short = v.get("ShortName")
            locale = v.get("Locale", "")
            gender = v.get("Gender", "")
            label = f"{short} — {locale} — {gender}"
            voice_items.append((short, label))
        voice_items.sort(key=lambda x: x[0].lower())
        return voice_items
    except:
        fallback = [
            ("vi-VN-HoaiMyNeural", "vi-VN-HoaiMyNeural — vi-VN — Female"),
            ("vi-VN-NamMinhNeural", "vi-VN-NamMinhNeural — vi-VN — Male"),
            ("en-US-JennyNeural", "en-US-JennyNeural — en-US — Female"),
        ]
        return fallback

async def _tts_save_async(text, voice, filepath):
    comm = edge_tts.Communicate(text, voice=voice)
    await comm.save(filepath)

def tts_save_tempfile(text, voice):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        asyncio.run(_tts_save_async(text, voice, tmp.name))
        return tmp.name
    except:
        try: os.remove(tmp.name)
        except: pass
        raise

# ---------------- SRT utils ----------------
def parse_srt(srt_path):
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(
        r'(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s+(.*?)\s*(?=\n\d+\n|\Z)',
        re.DOTALL
    )
    out = []
    for match in pattern.finditer(content):
        idx = match.group(1)
        start = match.group(2)
        end = match.group(3)
        text = match.group(4).replace('\n', ' ').strip()
        if ":" in text:
            spk, dialog = text.split(":",1)
            speaker = spk.strip()
            dialog = dialog.strip()
        else:
            speaker = "Narrator"
            dialog = text
        out.append((idx, start, end, speaker, dialog))
    return out

def segments_to_srt(segments, dest_lang="en", context_words=None, honorific_style="modern", progress_callback=None):
    subtitles = []
    total = len(segments)
    for i, seg in enumerate(segments):
        start = seg['start']
        end = seg['end']
        original_text = seg['text'].strip()
        translated_text = translate_text_with_context(original_text, dest_lang, context_words, honorific_style)
        subtitle = srt.Subtitle(
            index=i+1,
            start=datetime.timedelta(seconds=start),
            end=datetime.timedelta(seconds=end),
            content=translated_text
        )
        subtitles.append(subtitle)
        if progress_callback:
            progress_callback(int((i+1)/total*100))
    return srt.compose(subtitles)

# ---------------- Video -> SRT ----------------
def process_video(video_path, dest_lang="en", output_srt="output.srt", model_size="base", context_words=None, honorific_style="modern", progress_callback=None):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        temp_audio_path = temp_audio.name
    os.system(f'ffmpeg -y -i "{video_path}" -ar 16000 -ac 1 -f wav "{temp_audio_path}"')
    if progress_callback: progress_callback(5)
    segments, detected_lang = transcribe_audio(temp_audio_path, model_size=model_size)
    if progress_callback: progress_callback(40)
    srt_content = segments_to_srt(segments, dest_lang, context_words, honorific_style, progress_callback)
    with open(output_srt, "w", encoding="utf-8") as f: f.write(srt_content)
    os.remove(temp_audio_path)
    if progress_callback: progress_callback(100)
    return output_srt, detected_lang

# ---------------- GUI ----------------
def start_gui():
    root = tk.Tk()
    root.title(" Video -> SRT + Context & Honorifics")
    root.geometry("800x650")

    video_var = tk.StringVar()
    srt_var = tk.StringVar()
    out_var = tk.StringVar()
    context_var = tk.StringVar()
    honorific_var = tk.StringVar(value="modern")

    # Video selection
    tk.Label(root, text="Video:").pack(anchor="w", padx=10, pady=4)
    frame1 = tk.Frame(root); frame1.pack(fill="x", padx=10)
    tk.Entry(frame1, textvariable=video_var, width=60).pack(side="left", padx=4)
    tk.Button(frame1, text="Chọn video", command=lambda: video_var.set(filedialog.askopenfilename(filetypes=[("Video files","*.mp4;*.mkv;*.avi")]))).pack(side="left")

    # Context input
    tk.Label(root, text="Bối cảnh video:").pack(anchor="w", padx=10, pady=4)
    tk.Entry(root, textvariable=context_var, width=60).pack(anchor="w", padx=10)

    # Honorific combobox
    tk.Label(root, text="Xưng hô:").pack(anchor="w", padx=10, pady=4)
    ttk.Combobox(root, textvariable=honorific_var, values=["modern","ancient"], width=20).pack(anchor="w", padx=10)

    # Output SRT
    tk.Label(root, text="Output SRT:").pack(anchor="w", padx=10, pady=4)
    tk.Entry(root, textvariable=out_var, width=60).pack(anchor="w", padx=10)
    tk.Button(root, text="Chọn file SRT", command=lambda: out_var.set(filedialog.asksaveasfilename(defaultextension=".srt"))).pack(anchor="w", padx=10, pady=2)

    # Progress + log
    progress = ttk.Progressbar(root, length=700)
    progress.pack(pady=6)
    log = tk.Text(root, height=12); log.pack(fill="both", padx=10, pady=6)

    voices_list = fetch_all_voices()

    def update_progress(val):
        progress['value'] = val
        root.update_idletasks()
    def log_insert(text): log.insert(tk.END, text+"\n"); log.see(tk.END)

    def start_process():
        video_path = video_var.get()
        output_srt = out_var.get() or os.path.splitext(video_path)[0]+"_output.srt"
        context_words = context_var.get().split()
        honorific_style = honorific_var.get()
        if not video_path:
            messagebox.showerror("Lỗi","Chưa chọn video!")
            return
        log_insert(f"▶ Đang xử lý video: {video_path}")
        def task():
            try:
                result_srt, detected_lang = process_video(video_path, dest_lang="vi", output_srt=output_srt,
                                                          model_size="base", context_words=context_words, honorific_style=honorific_style,
                                                          progress_callback=update_progress)
                log_insert(f" Hoàn tất! File SRT: {result_srt}")
                log_insert(f"Ngôn ngữ gốc: {detected_lang}")
                messagebox.showinfo("Hoàn tất", f"File SRT đã tạo:\n{result_srt}")
            except Exception as e:
                log_insert(f" Lỗi: {e}")
                messagebox.showerror("Lỗi", str(e))
            finally:
                update_progress(0)
        threading.Thread(target=task, daemon=True).start()

    tk.Button(root, text="Start Processing", bg="green", fg="white", command=start_process).pack(pady=6)

    root.mainloop()

if __name__ == "__main__":
    start_gui()
