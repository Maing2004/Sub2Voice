"""
Ý tưởng: Tách audio từ video (mp4,mkv,avi) thành các track: vocals.wav và music.wav (gộp drums+bass+other)
file vocals.wav là giọng hát, music.wav là nhạc nền (không có giọng hát).
Yêu cầu:
    pip install demucs
    ffmpeg cần có trong PATH để gộp audio.
"""
import os, subprocess, threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --- Hàm tách audio bằng Demucs ---
def separate_audio(input_path, output_dir):
    subprocess.run(["demucs", "-o", output_dir, input_path], check=True)
    tracks = {}
    for root, _, files in os.walk(output_dir):
        for file in files:
            if file.endswith(".wav"):
                key = file.replace(".wav","")
                tracks[key] = os.path.join(root, file)
    return tracks

# --- Hàm gộp bass+drums+other thành music.wav ---
# --- Hàm gộp bass+drums+other thành music.wav ---
def merge_music_tracks(folder, delete_original=True):
    out_file = os.path.join(folder, "music.wav")
    inputs, tracks = [], []
    for name in ["drums.wav", "bass.wav", "other.wav"]:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            inputs.append("-i")
            inputs.append(path)
            tracks.append(path)

    if not tracks:
        return None
    
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", f"amix=inputs={len(tracks)}:duration=longest",
        out_file
    ]
    subprocess.run(cmd, check=True)

    # ✅ Xóa 3 file gốc sau khi gộp thành công
    if delete_original:
        for f in tracks:
            try:
                os.remove(f)
            except Exception as e:
                print(f"Không thể xóa {f}: {e}")

    return out_file


# --- GUI ---
class AudioExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 Video Audio Extractor (Demucs)")
        self.root.geometry("550x350")
        self.root.configure(bg="#2c2f33")

        self.file_path = ""

        # Label
        self.video_label = tk.Label(root, text="Chưa chọn video", fg="white", bg="#2c2f33")
        self.video_label.pack(pady=5)

        # Buttons
        tk.Button(root, text="Chọn Video", command=self.load_video,
                  font=("Arial", 12), bg="#7289da", fg="white", relief="flat").pack(pady=15, ipadx=10, ipady=5)
        tk.Button(root, text=" Bắt đầu tách âm thanh", command=self.start_process,
                  font=("Arial", 13, "bold"), bg="#faa61a", fg="black", relief="flat").pack(pady=15, ipadx=15, ipady=8)

        # Progress
        self.progress = ttk.Progressbar(root, mode="determinate", length=450)
        self.progress.pack(pady=10)

        # Log box
        self.log_box = tk.Text(root, height=10, bg="#23272a", fg="white")
        self.log_box.pack(fill="both", padx=10, pady=10)

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files","*.mp4;*.mkv;*.avi")])
        if path:
            self.file_path = path
            self.video_label.config(text=f"🎥 {os.path.basename(path)}")

    def start_process(self):
        threading.Thread(target=self.full_process).start()

    def full_process(self):
        if not self.file_path:
            return messagebox.showerror("Lỗi","Cần chọn video trước")
        outdir = "output"
        os.makedirs(outdir, exist_ok=True)

        try:
            self.progress["value"] = 0
            self.log(" Đang tách audio bằng Demucs...")

            tracks = separate_audio(self.file_path, outdir)
            self.progress["value"] = 70

            # Lấy folder chứa file demucs tạo ra
            track_folder = os.path.dirname(list(tracks.values())[0])

            # Gộp music
            music_file = merge_music_tracks(track_folder)
            self.progress["value"] = 100

            msg = " Hoàn tất!\nCác file đã tách:"
            for name, path in tracks.items():
                msg += f"\n- {name}: {path}"
            if music_file:
                msg += f"\n- music: {music_file} (gộp drums+bass+other)"
            messagebox.showinfo("Xong", msg)
            self.log(msg)

        except Exception as e:
            messagebox.showerror(" Lỗi", str(e))
            self.log(f"Error: {e}")

if __name__=="__main__":
    root = tk.Tk()
    AudioExtractorApp(root)
    root.mainloop()
