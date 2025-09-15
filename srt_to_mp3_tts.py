"""
Ý tưởng: Chuyển file SRT sang file audio MP3 sử dụng edge-tts. Vì edge-tts có nhiều giọng, nên có thể chọn giọng cho từng nhân vật.
Yêu cầu cài đặt:
    pip install edge-tts pydub
    ffmpeg cần có trong PATH để pydub export/play được.
"""
import re
import os
import io
import json
import asyncio
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pydub import AudioSegment
import edge_tts
from datetime import datetime

# ---------------- SRT utils ----------------
def parse_srt(srt_path):
    
    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    pattern = re.compile(
        r'(\d+)\s*\n\s*(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\s*\n|\n\s*\d+\s*\n|\Z)',
        re.DOTALL
    )
    out = []
    for match in pattern.finditer(content):
        idx = match.group(1).strip()
        start = match.group(2).strip()
        end = match.group(3).strip()
        text = match.group(4).strip().replace('\r', '').replace('\n', ' ')
        if ":" in text and not text.startswith("http") and len(text.split(":",1)[0]) <= 30:
            spk, dialog = text.split(":", 1)
            speaker = spk.strip()
            dialog = dialog.strip()
        else:
            speaker = "Narrator"
            dialog = text
        out.append((idx, start, end, speaker, dialog))
    return out

def split_text(text, max_length=200):
  
    words = text.split()
    chunks = []
    chunk = ""
    for w in words:
        if chunk == "":
            chunk = w
        elif len(chunk) + 1 + len(w) <= max_length:
            chunk += " " + w
        else:
            chunks.append(chunk)
            chunk = w
    if chunk:
        chunks.append(chunk)
    return chunks

def srt_time_to_ms(t):
    
    # Using datetime to parse; handle cases >24h not expected in subtitles
    dt = datetime.strptime(t, "%H:%M:%S,%f")
    return dt.hour*3600000 + dt.minute*60000 + dt.second*1000 + int(dt.microsecond/1000)

# ---------------- edge-tts helpers ----------------
async def _list_voices_async():
    return await edge_tts.list_voices()

def fetch_all_voices():
    """Return list of (short, label)"""
    try:
        voices = asyncio.run(_list_voices_async())
        voice_items = []
        for v in voices:
            short = v.get("ShortName")
            locale = v.get("Locale", "")
            gender = v.get("Gender", "")
            display = v.get("DisplayName") or short
            label = f"{short} — {locale} — {gender} — {display}"
            voice_items.append((short, label))
        voice_items.sort(key=lambda x: x[0].lower())
        return voice_items
    except Exception as e:
        print("Warning: cannot fetch edge-tts voices:", e)
        # fallback
        fallback = [
            ("vi-VN-HoaiMyNeural", "vi-VN-HoaiMyNeural — vi-VN — Female — HoaiMy"),
            ("vi-VN-NamMinhNeural", "vi-VN-NamMinhNeural — vi-VN — Male — NamMinh"),
            ("en-US-JennyNeural", "en-US-JennyNeural — en-US — Female — Jenny"),
            ("en-US-GuyNeural", "en-US-GuyNeural — en-US — Male — Guy"),
        ]
        return fallback

async def _tts_save_async(text, voice, filepath):
    comm = edge_tts.Communicate(text, voice=voice)
    await comm.save(filepath)

def tts_save_tempfile(text, voice):
    """Generate mp3 to a tempfile and return path (synchronous wrapper)."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        asyncio.run(_tts_save_async(text, voice, tmp.name))
        return tmp.name
    except Exception as e:
        try:
            os.remove(tmp.name)
        except:
            pass
        raise

# ---------------- Config save/load ----------------
def mapping_config_path_for_srt(srt_path):
    base = os.path.splitext(os.path.basename(srt_path))[0]
    dirn = os.path.dirname(srt_path) or "."
    return os.path.join(dirn, base + ".voice_map.json")

def save_voice_map(srt_path, voice_map):
    cfg = mapping_config_path_for_srt(srt_path)
    try:
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(voice_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Could not save voice map:", e)

def load_voice_map(srt_path):
    cfg = mapping_config_path_for_srt(srt_path)
    if os.path.exists(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("Could not load voice map:", e)
    return {}

# ---------------- Audio utils ----------------
def change_speed(sound, speed=1.0):
   
    if speed == 1.0:
        return sound
    new_frame_rate = int(sound.frame_rate * speed)
    sped_up = sound._spawn(sound.raw_data, overrides={"frame_rate": new_frame_rate})
    # set frame rate back to original so playback sample rate is consistent
    return sped_up.set_frame_rate(sound.frame_rate)

# ---------------- Conversion job ----------------
def conversion_job(srt_path, out_mp3, speaker_widgets_map, voices_list, log_widget, progress_bar, btn_start,
                   overflow_mode='cut', max_chunk_len=240):
   
    try:
        def _disable(state=True):
            try:
                btn_start.config(state="disabled" if state else "normal")
            except:
                pass
        _disable(True)

        subs = parse_srt(srt_path)
        total = len(subs)
        if total == 0:
            messagebox.showwarning("Warning", "Không tìm thấy subtitle hợp lệ trong SRT.")
            _disable(False)
            return

        # build voice_map from widgets (widgets might be simple objects with get())
        voice_map = {}
        for spk, cb in speaker_widgets_map.items():
            try:
                sel = cb.get().strip()
            except:
                sel = ""
            if sel == "":
                sel = voices_list[0][0] if voices_list else "vi-VN-HoaiMyNeural"
            # if combobox returned "label", find short name (if cb was label)
            # voices_list contains tuples (short,label)
            if sel not in [v[0] for v in voices_list]:
                # try match by label
                matched = None
                for s,label in voices_list:
                    if label == sel or s in sel:
                        matched = s; break
                sel = matched or voices_list[0][0]
            voice_map[spk] = sel

        save_voice_map(srt_path, voice_map)

        final = AudioSegment.silent(duration=0)
        current_pos = 0  # timeline position in ms
        for idx, (num, start, end, speaker, dialog) in enumerate(subs, 1):
            log_widget_insert(log_widget, f"[{idx}/{total}] {speaker}: {dialog[:120]}...\n")
            set_progress(progress_bar, int(idx/total*100))

            start_ms = srt_time_to_ms(start)
            end_ms = srt_time_to_ms(end)
            slot_dur = max(0, end_ms - start_ms)

            # if there's gap between current_pos and start_ms -> insert silence
            if start_ms > current_pos:
                gap = start_ms - current_pos
                final += AudioSegment.silent(duration=gap)
                current_pos += gap

            # generate TTS audio (may be longer/shorter than slot)
            chunks = split_text(dialog, max_length=max_chunk_len)
            seg_all = AudioSegment.silent(duration=0)
            for ch in chunks:
                try:
                    mp3tmp = tts_save_tempfile(ch, voice_map.get(speaker, voice_map.get("Narrator", list(voice_map.values())[0])))
                    seg = AudioSegment.from_file(mp3tmp, format="mp3")
                except Exception as e:
                    # On TTS failure, put a short beep or silence to keep timing (silence chosen)
                    log_widget_insert(log_widget, f"  [WARN] TTS failed for chunk: {e}\n")
                    seg = AudioSegment.silent(duration=500)
                finally:
                    try:
                        os.remove(mp3tmp)
                    except:
                        pass
                seg_all += seg

            seg_len = len(seg_all)

            # Fit seg_all into [start_ms, end_ms] based on overflow_mode
            if seg_len < slot_dur:
                # shorter -> pad end with silence
                pad = slot_dur - seg_len
                seg_all += AudioSegment.silent(duration=pad)
                final += seg_all
                current_pos = start_ms + slot_dur
            else:
                # seg_len >= slot_dur
                if overflow_mode == 'cut':
                    seg_cut = seg_all[:slot_dur]
                    final += seg_cut
                    current_pos = start_ms + slot_dur
                elif overflow_mode == 'speed':
                    # compute required speed factor
                    # speed = seg_len / slot_dur -> we need to shrink duration by speed
                    if slot_dur > 0:
                        speed_factor = seg_len / slot_dur
                        # apply speed change (note: change_speed expects >0)
                        seg_sped = change_speed(seg_all, speed=speed_factor)
                        # after speed change, length should be approximately slot_dur; adjust by slicing/padding
                        if len(seg_sped) > slot_dur:
                            seg_sped = seg_sped[:slot_dur]
                        elif len(seg_sped) < slot_dur:
                            seg_sped += AudioSegment.silent(duration=(slot_dur - len(seg_sped)))
                        final += seg_sped
                        current_pos = start_ms + slot_dur
                    else:
                        # if slot_dur==0 fallback to cut first ms
                        final += seg_all[:1]
                        current_pos = start_ms + 1
                elif overflow_mode == 'overflow':
                    # allow it to overflow: append full seg_all; this will push timeline forward
                    final += seg_all
                    current_pos = start_ms + seg_len
                else:
                    # unknown mode: default to cut
                    final += seg_all[:slot_dur]
                    current_pos = start_ms + slot_dur

        # Export final MP3
        final.export(out_mp3, format="mp3")
        set_progress(progress_bar, 100)
        messagebox.showinfo("Hoàn tất", f"Đã tạo file: {out_mp3}")
    except Exception as e:
        messagebox.showerror("Lỗi", str(e))
    finally:
        _disable(False)

# small GUI helpers (thread-safe updates)
def log_widget_insert(widget, text):
    def inner():
        widget.insert(tk.END, text)
        widget.see(tk.END)
    widget.after(0, inner)

def set_progress(widget, val):
    def inner():
        widget['value'] = val
    widget.after(0, inner)

# ---------------- GUI ----------------
def start_gui():
    root = tk.Tk()
    root.title("Chuyển file SRT sang Audio")
    root.geometry("980x760")

    lbl_fetch = tk.Label(root, text="Đang tải danh sách giọng từ edge-tts (mất vài giây)...")
    lbl_fetch.pack(anchor="w", padx=10, pady=6)
    root.update()

    voices_list = fetch_all_voices()
    lbl_fetch.destroy()

    srt_var = tk.StringVar()
    out_var = tk.StringVar()

    frm_top = tk.Frame(root)
    frm_top.pack(fill="x", padx=10, pady=6)

    tk.Label(frm_top, text="File SRT:").grid(row=0, column=0, sticky="w")
    tk.Entry(frm_top, textvariable=srt_var, width=95).grid(row=0, column=1, padx=6)
    def choose_srt():
        p = filedialog.askopenfilename(title="Chọn file SRT", filetypes=[("Subtitle files", "*.srt")])
        if p:
            srt_var.set(p)
            load_and_populate_speakers(p)
    tk.Button(frm_top, text="Chọn", command=choose_srt).grid(row=0, column=2, padx=6)

    tk.Label(frm_top, text="MP3 đầu ra:").grid(row=1, column=0, sticky="w", pady=6)
    tk.Entry(frm_top, textvariable=out_var, width=95).grid(row=1, column=1, padx=6)
    def choose_out():
        default = os.path.splitext(os.path.basename(srt_var.get()))[0] + ".mp3" if srt_var.get() else "output.mp3"
        p = filedialog.asksaveasfilename(title="Chọn MP3 đầu ra", defaultextension=".mp3", initialfile=default, filetypes=[("MP3 files","*.mp3")])
        if p:
            out_var.set(p)
    tk.Button(frm_top, text="Chọn", command=choose_out).grid(row=1, column=2, padx=6)

    # overflow mode controls
    frm_mode = tk.Frame(root)
    frm_mode.pack(fill="x", padx=10, pady=2)
    tk.Label(frm_mode, text="Chế độ khi audio dài hơn slot:").pack(side="left", padx=6)
    overflow_var = tk.StringVar(value="cut")
    tk.Radiobutton(frm_mode, text="Cắt", variable=overflow_var, value="cut").pack(side="left", padx=6)
    tk.Radiobutton(frm_mode, text="Tăng tốc (có thể đổi pitch)", variable=overflow_var, value="speed").pack(side="left", padx=6)
    tk.Radiobutton(frm_mode, text="Cho phép tràn (không cắt)", variable=overflow_var, value="overflow").pack(side="left", padx=6)
    tk.Label(frm_mode, text="Max chunk text length:").pack(side="left", padx=12)
    max_chunk_spin = tk.Spinbox(frm_mode, from_=80, to=1000, increment=10, width=6)
    max_chunk_spin.delete(0, "end")
    max_chunk_spin.insert(0, "240")
    max_chunk_spin.pack(side="left", padx=6)

    tk.Label(root, text="Danh sách nhân vật (chọn giọng cho từng nhân vật):").pack(anchor="w", padx=10, pady=6)
    frame_speakers = tk.Frame(root, relief=tk.RIDGE, bd=1)
    frame_speakers.pack(fill="both", expand=False, padx=10, pady=4)

    canvas = tk.Canvas(frame_speakers, height=260)
    scrollbar = ttk.Scrollbar(frame_speakers, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)
    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0,0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    speaker_widgets = {}

    def load_and_populate_speakers(path):
        # clear
        for w in scrollable_frame.winfo_children():
            w.destroy()
        speaker_widgets.clear()

        subs = parse_srt(path)
        speakers = sorted(set([s for (_,_,_,s,_) in subs]))
        if not speakers:
            tk.Label(scrollable_frame, text="Không tìm thấy nhân vật / subtitle").pack(anchor="w", padx=6, pady=4)
            return

        saved_map = load_voice_map(path)

        for spk in speakers:
            row = tk.Frame(scrollable_frame)
            row.pack(fill="x", padx=6, pady=3)
            lbl = tk.Label(row, text=spk, width=28, anchor="w")
            lbl.pack(side="left")

            # combobox values are full label strings
            cb_var = tk.StringVar()
            cb = ttk.Combobox(row, textvariable=cb_var, values=[lab for (_,lab) in voices_list], width=68)
            # default selection
            default_voice = saved_map.get(spk)
            if default_voice:
                found_label = next((lab for s,lab in voices_list if s == default_voice), None)
                cb.set(found_label if found_label else voices_list[0][1])
            else:
                if spk.lower() == "narrator":
                    found_label = next((lab for s,lab in voices_list if s.startswith("vi-VN")), None)
                    cb.set(found_label if found_label else voices_list[0][1])
                else:
                    cb.set(voices_list[0][1])
            cb.pack(side="left", padx=6)

            def make_preview(speaker_name, combobox):
                def _preview():
                    label_text = combobox.get()
                    short = next((s for s,l in voices_list if l == label_text), None)
                    if short is None:
                        short = voices_list[0][0]
                    preview_text = f"Đây là giọng của {speaker_name}."
                    def _run_preview():
                        try:
                            tmpmp3 = tts_save_tempfile(preview_text, short)
                            seg = AudioSegment.from_file(tmpmp3, format="mp3")
                            play_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                            play_tmp.close()
                            seg.export(play_tmp.name, format="mp3")
                            try:
                                if os.name == "nt":
                                    os.startfile(play_tmp.name)
                                else:
                                    os.system(f'xdg-open "{play_tmp.name}" 2>/dev/null || open "{play_tmp.name}"')
                            except Exception:
                                pass
                        except Exception as e:
                            messagebox.showerror("Preview error", str(e))
                    threading.Thread(target=_run_preview, daemon=True).start()
                return _preview
            btn_preview = tk.Button(row, text="Preview", command=make_preview(spk, cb), width=10)
            btn_preview.pack(side="left", padx=6)
            speaker_widgets[spk] = cb

    frame_progress = tk.Frame(root)
    frame_progress.pack(fill="x", padx=10, pady=8)
    progress = ttk.Progressbar(frame_progress, length=940)
    progress.pack(fill="x", padx=6, pady=4)

    tk.Label(root, text="Log tiến độ:").pack(anchor="w", padx=10)
    log = tk.Text(root, height=14)
    log.pack(fill="both", expand=False, padx=10, pady=6)

    frame_bottom = tk.Frame(root)
    frame_bottom.pack(fill="x", padx=10, pady=6)
    btn_start = tk.Button(frame_bottom, text="Bắt đầu chuyển đổi", bg="green", fg="white",
                          command=lambda: start_conversion_thread(srt_var, out_var, speaker_widgets, voices_list, log, progress, btn_start, overflow_var.get(), int(max_chunk_spin.get())))
    btn_start.pack(side="left", padx=6)

    def save_mapping_now():
        if not srt_var.get():
            messagebox.showwarning("Cảnh báo", "Chưa chọn file SRT.")
            return
        mapping = {}
        for spk, cb in speaker_widgets.items():
            label_text = cb.get()
            short = next((s for s,l in voices_list if l == label_text), None)
            if short is None:
                short = voices_list[0][0]
            mapping[spk] = short
        save_voice_map(srt_var.get(), mapping)
        messagebox.showinfo("Lưu", "Đã lưu cấu hình giọng cho file SRT này.")

    btn_savecfg = tk.Button(frame_bottom, text="Lưu cấu hình giọng", command=save_mapping_now)
    btn_savecfg.pack(side="left", padx=6)

    def start_conversion_thread(srt_var, out_var, speaker_widgets_map, voices_list_local, log_widget, progress_bar_widget, btn_start_widget, overflow_mode_local, max_chunk_len_local):
        if not srt_var.get():
            messagebox.showwarning("Cảnh báo", "Chưa chọn file SRT.")
            return
        if not out_var.get():
            messagebox.showwarning("Cảnh báo", "Chưa chọn file MP3 đầu ra.")
            return
        # convert combobox label -> short name
        widget_map_for_job = {}
        for spk, cb in speaker_widgets_map.items():
            chosen_label = cb.get()
            chosen_short = next((s for s,l in voices_list_local if l == chosen_label), None)
            if chosen_short is None:
                chosen_short = voices_list_local[0][0]
            class SimpleCB:
                def __init__(self, val): self._v = val
                def get(self): return self._v
            widget_map_for_job[spk] = SimpleCB(chosen_short)

        th = threading.Thread(target=conversion_job, args=(srt_var.get(), out_var.get(), widget_map_for_job, voices_list_local, log_widget, progress_bar_widget, btn_start_widget, overflow_mode_local, max_chunk_len_local), daemon=True)
        th.start()

    root.mainloop()

if __name__ == "__main__":
    start_gui()
