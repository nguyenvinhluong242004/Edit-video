import os
import ffmpeg
import tempfile
import json
import numpy as np
from PIL import Image
import gradio as gr
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Thiết lập ffmpeg path
os.environ["PATH"] += os.pathsep + r"D:\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"
os.makedirs("outputs", exist_ok=True)

TIMEOUT = 300  # 5 phút

### ============================
### API 1: Ảnh + nhạc => video
### ============================

def create_single_video(args):
    img, dur, output_path, width, height, fps = args
    temp_img_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
    Image.fromarray(img).save(temp_img_path)

    d_frames = int(dur * fps)
    font_path = "fonts/Roboto-VariableFont_wdth_wght.ttf"

    vf = (
        f"scale=3200:-1,"
        f"zoompan=z='min(zoom+0.0002,1.5)':x='floor(iw/2-(iw/zoom/2))':y='floor(ih/2-(ih/zoom/2))':d={d_frames}:s={width}x{height}:fps={fps}"
    )

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        stream = ffmpeg.input(temp_img_path, loop=1, t=dur)
        stream = stream.output(output_path, **{
            'vf': vf,
            't': dur,
            'pix_fmt': 'yuv420p',
            'crf': '20',
            'c:v': 'libx264',
            'an': None
        })
        print("FFmpeg command:", stream.compile())
        out, err = stream.run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        print('FFmpeg Error:', e.stderr.decode('utf-8'))
        raise
    finally:
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

    return output_path

def create_video_from_images(images, durations, audio_path, output_path, fps=60):
    height, width, _ = images[0].shape
    temp_dir = tempfile.mkdtemp()
    video_paths = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [
            (img, dur, os.path.join(temp_dir, f"temp_{i}.mp4"), width, height, fps)
            for i, (img, dur) in enumerate(zip(images, durations))
        ]
        try:
            video_paths = list(executor.map(create_single_video, tasks, timeout=TIMEOUT))
        except TimeoutError:
            print("Timeout Error: Operation took too long to complete.")
            return None

    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, 'w') as f:
        for path in video_paths:
            f.write(f"file '{path}'\n")

    ffmpeg.input(concat_file, format='concat', safe=0).output(output_path, c='copy', an=None).overwrite_output().run()

    final_output_path = output_path.replace(".mp4", "_with_audio.mp4")
    video_input = ffmpeg.input(output_path)
    audio_input = ffmpeg.input(audio_path)
    ffmpeg.output(video_input, audio_input, final_output_path, vcodec='libx264', acodec='aac', shortest=None).overwrite_output().run()

    for path in video_paths:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(concat_file):
        os.remove(concat_file)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)

    return final_output_path

def generate_video(image_files, duration_input, audio_file, fps=60):
    try:
        durations = json.loads(duration_input)
    except Exception as e:
        return None, f"❌ Lỗi khi phân tích đầu vào:\n{e}"

    if len(image_files) != len(durations):
        return None, "❌ Số lượng ảnh và durations phải bằng nhau!"

    try:
        os.makedirs("outputs", exist_ok=True)
        audio_path = audio_file.name
        output_video_path = os.path.join("outputs", "temp_output.mp4")

        images = []
        for idx, img_file in enumerate(image_files):
            try:
                img_pil = Image.open(img_file).convert("RGB")
                img = np.array(img_pil)
                images.append(img)
                print(f"✅ Ảnh {idx+1}: {img_file.name} - kích thước {img.shape}")
            except Exception as e:
                print(f"❌ Không đọc được ảnh {idx+1}: {img_file.name} - lỗi: {e}")

        if not images:
            return None, "❌ Không có ảnh nào hợp lệ để tạo video!"

        final_video_path = create_video_from_images(images, durations, audio_path, output_video_path, fps)
        if final_video_path is None:
            return None, "❌ Quá trình tạo video đã bị timeout!"
        return final_video_path, "✅ Video tạo thành công!"
    except Exception as e:
        import traceback
        return None, f"❌ Lỗi khi tạo video:\n{traceback.format_exc()}"

image_to_video_tab = gr.Interface(
    fn=generate_video,
    inputs=[
        gr.File(file_types=["image"], label="Ảnh", file_count="multiple"),
        gr.Textbox(label="Durations (giây)", placeholder="[3, 4, 5]"),
        gr.File(file_types=["audio"], label="Nhạc nền"),
        gr.Slider(minimum=1, maximum=120, step=1, label="FPS", value=60),
    ],
    outputs=[
        gr.Video(label="Video ảnh"),
        gr.Textbox(label="Trạng thái"),
    ],
    title="API 1 - Ảnh thành video + nhạc",
)

### ============================
### API 2: Text => video
### ============================

def wrap_text(text, max_width=1060, font_size=20):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) * font_size <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line.strip())
            current_line = word
    if current_line:
        lines.append(current_line.strip())
    return "\n".join(lines)

def calculate_text_height(text, font_size=20, line_spacing=10):
    lines = text.split("\n")
    return len(lines) * font_size + (len(lines) - 1) * line_spacing

import subprocess

def overlay_subtitles(video_path, scripts, durations, output_path, width=592, height=800):
    try:
        start_times = [0]
        for i in range(len(durations) - 1):
            start_times.append(start_times[-1] + durations[i])

        font_path = "fonts/Roboto-VariableFont_wdth_wght.ttf"
        filter_complex = ""

        for i, (script, dur, start) in enumerate(zip(scripts, durations, start_times)):
            wrapped = wrap_text(script, max_width=width + 460)
            wrapped = wrapped.replace(":", "\\:").replace("'", "\\'")
            text_height = calculate_text_height(wrapped)
            y = height - text_height - 30
            end = start + dur

            filter_complex += (
                f"drawtext=text='{wrapped}':fontsize=20:fontcolor=white:x=(w-text_w)/2:y={y}:"
                f"fontfile='{font_path}':box=1:boxcolor=black@0.5:boxborderw=10:line_spacing=10:"
                f"enable='between(t,{start},{end})',"
            )

        filter_complex = filter_complex.rstrip(',')

        command = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "veryfast",
        ]

        # Kiểm tra xem có audio không
        probe = ffmpeg.probe(video_path)
        has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])

        if has_audio:
            command += ["-c:a", "aac", "-shortest"]

        command += [output_path]

        print("Running command:", " ".join(command))
        subprocess.run(command, check=True)

        return output_path
    except subprocess.CalledProcessError as e:
        return f"❌ FFmpeg failed: {e}"
    except Exception as e:
        import traceback
        return f"❌ Lỗi khác: {traceback.format_exc()}"

def generate_video_2(video_file, script_input, duration_input):
    try:
        scripts = json.loads(script_input)
        durations = json.loads(duration_input)
    except Exception as e:
        return None, f"❌ Lỗi khi phân tích đầu vào:\n{e}"

    if len(scripts) != len(durations):
        return None, "❌ Scripts và durations phải có độ dài bằng nhau!"

    try:
        os.makedirs("outputs", exist_ok=True)
        video_path = video_file.name
        output_video_path = os.path.join("outputs", "video_with_subtitles.mp4")

        # 👉 Lấy width, height từ video
        probe = ffmpeg.probe(video_path)
        video_stream = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        result = overlay_subtitles(video_path, scripts, durations, output_video_path, width, height)
        if isinstance(result, str) and result.startswith("❌"):
            return None, result
        return result, "✅ Video với phụ đề tạo thành công!"
    except Exception as e:
        import traceback
        return None, f"❌ Lỗi khi tạo video:\n{traceback.format_exc()}"
    
text_to_video_tab = gr.Interface(
    fn=generate_video_2,
    inputs=[
        gr.File(file_types=["video"], label="Video chính"),
        gr.Textbox(label="Scripts", placeholder="['Xin chào', 'Đây là phụ đề']"),
        gr.Textbox(label="Durations (giây)", placeholder="[3, 4]"),
    ],
    outputs=[
        gr.Video(label="Video với phụ đề"),
        gr.Textbox(label="Trạng thái"),
    ],
    title="API 2 - Chèn phụ đề vào video",
)

### ============================
### Giao diện chính
### ============================

demo = gr.TabbedInterface(
    interface_list=[
        image_to_video_tab,
        text_to_video_tab
    ],
    tab_names=["Tạo video từ ảnh", "Tạo video từ chữ", "Ghép 2 video"]
)

if __name__ == "__main__":
    demo.queue().launch()