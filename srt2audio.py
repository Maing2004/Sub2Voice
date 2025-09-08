import pysrt
from gtts import gTTS
import subprocess
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ---- Hàm chuyển SRT -> MP3 lớn ----
def srt_to_mp3(srt_file, output_file, ffmpeg_path):
    temp_folder = "temp_audio"
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)

    subs = pysrt.open(srt_file, encoding='utf-8')

    def clean_text(text):
        text = re.sub(r'<.*?>', '', text)
        text = text.replace('\n', ' ')
        return text.strip()

    concat_list = []

    # ---- Tạo các file MP3 nhỏ ----
    for i, sub in enumerate(subs):
        text = clean_text(sub.text)
        start_ms = sub.start.ordinal
        end_ms = sub.end.ordinal
        duration_sec = (end_ms - start_ms) / 1000

        log_text.set(f"Tạo audio {i+1}/{len(subs)}...")
        root.update_idletasks()

        temp_file = os.path.join(temp_folder, f"{i}.mp3")
        tts = gTTS(text, lang='vi')
        tts.save(temp_file)

        # ---- Thêm silence nếu audio ngắn hơn thời gian hiển thị ----
        padded_file = os.path.join(temp_folder, f"{i}_padded.mp3")
        subprocess.run([
            ffmpeg_path,
            "-y",
            "-i", temp_file,
            "-af", f"apad=pad_dur={duration_sec}",
            "-t", str(duration_sec),
            padded_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        concat_list.append(padded_file)
        progress['value'] = (i+1)/len(subs)*100
        root.update_idletasks()

    # ---- Tạo file danh sách cho ffmpeg concat ----
    concat_txt = os.path.join(temp_folder, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for file in concat_list:
            f.write(f"file '{file}'\n")

    # ---- Ghép tất cả file MP3 nhỏ thành 1 file lớn ----
    subprocess.run([
        ffmpeg_path,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt,
        "-c", "copy",
        output_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- Xóa các file tạm ----
    for file in concat_list:
        os.remove(file)
    if os.path.exists(concat_txt):
        os.remove(concat_txt)
    for file in os.listdir(temp_folder):
        temp_path = os.path.join(temp_folder, file)
        if os.path.isfile(temp_path):
            os.remove(temp_path)
    os.rmdir(temp_folder)

    messagebox.showinfo("Hoàn thành", f"File {output_file} đã được tạo!")

# ---- UI Tkinter ----
def select_srt():
    file_path = filedialog.askopenfilename(filetypes=[("SRT files", "*.srt")])
    if file_path:
        srt_entry.delete(0, tk.END)
        srt_entry.insert(0, file_path)

def select_output():
    file_path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3 files", "*.mp3")])
    if file_path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, file_path)

def start_conversion():
    srt_file = srt_entry.get()
    output_file = output_entry.get()
    ffmpeg_path = ffmpeg_entry.get()
    if not all([srt_file, output_file, ffmpeg_path]):
        messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn đầy đủ file SRT, MP3 và FFmpeg")
        return
    srt_to_mp3(srt_file, output_file, ffmpeg_path)

# ---- Thiết lập giao diện ----
root = tk.Tk()
root.title("SRT -> MP3 Converter")
root.geometry("600x250")

tk.Label(root, text="Chọn file SRT:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
srt_entry = tk.Entry(root, width=50)
srt_entry.grid(row=0, column=1, padx=5)
tk.Button(root, text="Chọn", command=select_srt).grid(row=0, column=2, padx=5)

tk.Label(root, text="Lưu file MP3:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
output_entry = tk.Entry(root, width=50)
output_entry.grid(row=1, column=1, padx=5)
tk.Button(root, text="Chọn", command=select_output).grid(row=1, column=2, padx=5)

tk.Label(root, text="Đường dẫn FFmpeg:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
ffmpeg_entry = tk.Entry(root, width=50)
ffmpeg_entry.insert(0, r"C:\ffmpeg\bin\ffmpeg.exe")
ffmpeg_entry.grid(row=2, column=1, padx=5)

progress = ttk.Progressbar(root, length=500)
progress.grid(row=3, column=0, columnspan=3, pady=15, padx=5)

log_text = tk.StringVar()
log_label = tk.Label(root, textvariable=log_text, fg="blue")
log_label.grid(row=4, column=0, columnspan=3)

tk.Button(root, text="Bắt đầu chuyển đổi", command=start_conversion, bg="green", fg="white").grid(row=5, column=0, columnspan=3, pady=15)

root.mainloop()
