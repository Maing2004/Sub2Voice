Chức năng 1 : 🎙️ SRT to MP3 Converter
🚀 Tính năng
- Hỗ trợ nhập file .srt.
- Chọn giọng đọc khác nhau cho từng nhân vật.
- Xem trước giọng đọc trước khi xuất file.
- Xuất file MP3 với canh chỉnh theo thời gian phụ đề.
- Tùy chọn xử lý khi thoại dài hơn slot thời gian:
    +✂️ Cắt bớt
    +⏩ Tăng tốc độ đọc
    +↔️ Cho phép tràn (đẩy timeline về sau)
- Lưu lại cấu hình giọng đọc (.voice_map.json) cho mỗi file SRT.

📦 Yêu cầu cài đặt:
1. Python
- Cần Python 3.9+.
- Tải Python tại: https://www.python.org/downloads/
2. Thư viện Python
- Chạy lệnh: pip install edge-tts pydub
3. FFmpeg
- Tải tại: https://ffmpeg.org/download.html
- Giải nén và thêm thư mục bin/ của FFmpeg vào biến môi trường PATH.
- Kiểm tra cài đặt: bật cmd và gõ lệnh " ffmpeg -version "

🖥️ Cách sử dụng:
1. Mở cmd nhập lệnh : python srt_to_mp3.py
2.Trong giao diện:
- Chọn file SRT.
- Chọn file MP3 đầu ra.
- Chọn giọng cho từng nhân vật.
- Nhấn Bắt đầu chuyển đổi.
3. Sau khi chạy xong, bạn sẽ có file MP3 hoàn chỉnh theo phụ đề.

📂 Cấu trúc file sinh ra
1. output.mp3 – file audio đã ghép thoại.
2. yourfile.voice_map.json – cấu hình mapping nhân vật → giọng đọc.

🎯 Ví dụ giọng đọc (Edge TTS)
Một số giọng phổ biến:
vi-VN-HoaiMyNeural – Nữ, tiếng Việt.
vi-VN-NamMinhNeural – Nam, tiếng Việt.
en-US-JennyNeural – Nữ, tiếng Anh (Mỹ).
en-US-GuyNeural – Nam, tiếng Anh (Mỹ).

DANH SÁCH CÁC GIỌNG ĐỌC LƯU TRONG FILE : voices.txt
