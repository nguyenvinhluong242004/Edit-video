# import ffmpeg
# import os
# import numpy as np
# from PIL import Image
# import json
# import gradio as gr
# from concurrent.futures import ThreadPoolExecutor, TimeoutError
# import tempfile

# os.environ["PATH"] += os.pathsep + r"D:\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"

# # Timeout for the entire operation (in seconds)
# TIMEOUT = 300  # 5 minutes

# def wrap_text(text, max_width=1060, font_size=20):
#     words = text.split()
#     lines = []
#     current_line = ""
#     for word in words:
#         if len(current_line + " " + word) * font_size <= max_width:
#             current_line += " " + word
#         else:
#             lines.append(current_line.strip())
#             current_line = word
#     if current_line:
#         lines.append(current_line.strip())
#     return "\n".join(lines)

# def calculate_text_height(text, font_size=20, line_spacing=10):
#     lines = text.split("\n")
#     return len(lines) * font_size + (len(lines) - 1) * line_spacing

# def create_single_video(args):
#     img, script, dur, output_path, width, height, fps = args
#     temp_img_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
#     Image.fromarray(img).save(temp_img_path)

#     d_frames = int(dur * fps)
#     wrapped_text = wrap_text(script, width + 460, font_size=20)
#     wrapped_text = wrapped_text.replace(":", "\\:").replace("'", "\\'")
#     text_height = calculate_text_height(wrapped_text, font_size=20, line_spacing=10)
#     y_position = height - text_height - 30

#     # font_path = "fonts/Roboto-VariableFont_wdth\,wght.ttf"

#     # font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
#     font_path = "fonts/Roboto-VariableFont_wdth\,wght.ttf"
#     # if not os.path.exists(font_path):
#     #     raise FileNotFoundError(f"Font file {font_path} not found!")

#     vf = (
#         f"scale=3200:-1,"
#         f"zoompan=z='min(zoom+0.0002,1.5)':x='floor(iw/2-(iw/zoom/2))':y='floor(ih/2-(ih/zoom/2))':d={d_frames}:s={width}x{height}:fps={fps},"
#         f"drawtext=text='{wrapped_text}':fontsize=20:fontcolor=white:x=(w-text_w)/2:y={y_position}:"
#         f"fontfile={font_path}:box=1:boxcolor=black@0.5:boxborderw=10:line_spacing=10"
#     )

#     try:
#         os.makedirs(os.path.dirname(output_path), exist_ok=True)
#         stream = ffmpeg.input(temp_img_path, loop=1, t=dur)
#         stream = stream.output(output_path, **{
#             'vf': vf,
#             't': dur,
#             'pix_fmt': 'yuv420p',
#             'crf': '20',
#             'c:v': 'libx264',
#             'an': None
#         })
#         print("FFmpeg command:", stream.compile())
#         out, err = stream.run(capture_stdout=True, capture_stderr=True)
#     except ffmpeg.Error as e:
#         print('FFmpeg Error:', e.stderr.decode('utf-8'))
#         raise
#     finally:
#         if os.path.exists(temp_img_path):
#             os.remove(temp_img_path)

#     return output_path

# def create_video_from_images(images, scripts, durations, audio_path, output_path, fps=60):
#     height, width, _ = images[0].shape
#     temp_dir = tempfile.mkdtemp()
#     video_paths = []

#     with ThreadPoolExecutor(max_workers=2) as executor:
#         tasks = [
#             (img, script, dur, os.path.join(temp_dir, f"temp_{i}.mp4"), width, height, fps)
#             for i, (img, script, dur) in enumerate(zip(images, scripts, durations))
#         ]
#         try:
#             video_paths = list(executor.map(create_single_video, tasks, timeout=TIMEOUT))
#         except TimeoutError:
#             print("Timeout Error: Operation took too long to complete.")
#             return None

#     concat_file = os.path.join(temp_dir, "concat.txt")
#     with open(concat_file, 'w') as f:
#         for path in video_paths:
#             f.write(f"file '{path}'\n")

#     ffmpeg.input(concat_file, format='concat', safe=0).output(output_path, c='copy', an=None).overwrite_output().run()

#     final_output_path = output_path.replace(".mp4", "_with_audio.mp4")
#     video_input = ffmpeg.input(output_path)
#     audio_input = ffmpeg.input(audio_path)
#     ffmpeg.output(video_input, audio_input, final_output_path, vcodec='libx264', acodec='aac', shortest=None).overwrite_output().run()

#     for path in video_paths:
#         if os.path.exists(path):
#             os.remove(path)
#     if os.path.exists(concat_file):
#         os.remove(concat_file)
#     if os.path.exists(temp_dir):
#         os.rmdir(temp_dir)

#     return final_output_path

# def generate_video(image_files, script_input, duration_input, audio_file, fps=60):
#     try:
#         scripts = json.loads(script_input)
#         durations = json.loads(duration_input)
#     except Exception as e:
#         return None, f"❌ Lỗi khi phân tích đầu vào:\n{e}"

#     if len(image_files) != len(scripts) or len(scripts) != len(durations):
#         return None, "❌ Số lượng ảnh, scripts và durations phải bằng nhau!"

#     try:
#         os.makedirs("outputs", exist_ok=True)
#         audio_path = audio_file.name
#         output_video_path = os.path.join("outputs", "temp_output.mp4")

#         images = []
#         for idx, img_file in enumerate(image_files):
#             try:
#                 img_pil = Image.open(img_file).convert("RGB")
#                 img = np.array(img_pil)
#                 images.append(img)
#                 print(f"✅ Ảnh {idx+1}: {img_file.name} - kích thước {img.shape}")
#             except Exception as e:
#                 print(f"❌ Không đọc được ảnh {idx+1}: {img_file.name} - lỗi: {e}")

#         if not images:
#             return None, "❌ Không có ảnh nào hợp lệ để tạo video!"

#         final_video_path = create_video_from_images(images, scripts, durations, audio_path, output_video_path, fps)
#         if final_video_path is None:
#             return None, "❌ Quá trình tạo video đã bị timeout!"
#         return final_video_path, "✅ Video tạo thành công!"
#     except Exception as e:
#         import traceback
#         return None, f"❌ Lỗi khi tạo video:\n{traceback.format_exc()}"

# demo = gr.Interface(
#     fn=generate_video,
#     inputs=[
#         gr.File(file_types=["image"], label="Ảnh (nhiều)", file_count="multiple"),
#         gr.Textbox(label="Scripts (danh sách)", placeholder="['Chào bạn', 'Video demo']"),
#         gr.Textbox(label="Durations (giây)", placeholder="[3, 4]"),
#         gr.File(file_types=["audio"], label="Nhạc nền (.mp3 hoặc .wav)"),
#         gr.Slider(minimum=1, maximum=120, step=1, label="FPS (frame/giây)", value=60),
#     ],
#     outputs=[
#         gr.Video(label="Video kết quả"),
#         gr.Textbox(label="Trạng thái", interactive=False),
#     ],
#     title="Tạo video từ ảnh, chữ và nhạc",
#     description="Upload nhiều ảnh + đoạn chữ + nhạc nền để tạo video tự động."
# )

# if __name__ == "__main__":
#     demo.queue().launch()

import os, ffmpeg, tempfile, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gradio as gr

import ffmpeg
import os
import numpy as np
from PIL import Image
import json
import gradio as gr
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import tempfile

# Thiết lập ffmpeg path
os.environ["PATH"] += os.pathsep + r"D:\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"
os.makedirs("outputs", exist_ok=True)

### ============================
### API 1: Ảnh + nhạc => video
### ============================

def create_video_from_images(images, durations, audio_path, output_path, fps=60):
    temp_dir = tempfile.mkdtemp()
    video_paths = []

    for i, (img, dur) in enumerate(zip(images, durations)):
        img_path = os.path.join(temp_dir, f"img_{i}.png")
        Image.fromarray(img).save(img_path)
        out_path = os.path.join(temp_dir, f"video_{i}.mp4")

        ffmpeg.input(img_path, loop=1, t=dur).output(
            out_path, vcodec='libx264', pix_fmt='yuv420p', t=dur, r=fps
        ).overwrite_output().run()
        video_paths.append(out_path)

    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, 'w') as f:
        for p in video_paths:
            f.write(f"file '{p}'\n")

    output_temp = output_path.replace(".mp4", "_tmp.mp4")
    ffmpeg.input(concat_file, format='concat', safe=0).output(output_temp, c='copy').overwrite_output().run()
    
    ffmpeg.input(output_temp).output(audio_path, output_path, shortest=None, vcodec='libx264', acodec='aac').overwrite_output().run()
    return output_path

def api_image_to_video(image_files, duration_input, audio_file, fps):
    try:
        durations = json.loads(duration_input)
        if len(image_files) != len(durations):
            return None, "❌ Số lượng ảnh và durations phải bằng nhau!"

        images = [np.array(Image.open(f).convert("RGB")) for f in image_files]
        output_path = "outputs/video_from_images.mp4"
        video_path = create_video_from_images(images, durations, audio_file.name, output_path, fps)
        return video_path, "✅ Video ảnh đã tạo thành công!"
    except Exception as e:
        return None, f"❌ Lỗi: {str(e)}"

image_to_video_tab = gr.Interface(
    fn=api_image_to_video,
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

def create_text_frame(text, width=1280, height=720):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = "fonts/Roboto-VariableFont_wdth,wght.ttf"
    if not os.path.exists(font_path):
        raise Exception(f"Không tìm thấy font: {font_path}")
    
    font_size = 20
    line_spacing = 10
    font = ImageFont.truetype(font_path, font_size)

    wrapped_text = wrap_text(text, max_width=width + 460, font_size=font_size)
    lines = wrapped_text.split("\n")

    # Tổng chiều cao
    total_text_height = calculate_text_height(wrapped_text, font_size=font_size, line_spacing=line_spacing)

    # Tính chiều rộng dài nhất trong các dòng
    max_line_width = max(draw.textlength(line, font=font) for line in lines)

    # Căn giữa toàn bộ đoạn văn bản
    x = (width - max_line_width) // 2
    y = height - total_text_height- 30

    draw.multiline_text((x, y), wrapped_text, fill="white", font=font, spacing=line_spacing, align="center")
    return np.array(img)


def text_to_video(scripts, durations, output_path, fps, width, height):
    temp_dir = tempfile.mkdtemp()
    video_paths = []

    for i, (text, dur) in enumerate(zip(scripts, durations)):
        img = create_text_frame(text, width=width, height=height)
        temp_img = os.path.join(temp_dir, f"text_{i}.png")
        Image.fromarray(img).save(temp_img)
        out_path = os.path.join(temp_dir, f"vid_text_{i}.mp4")
        ffmpeg.input(temp_img, loop=1, t=dur).output(out_path, vcodec='libx264', pix_fmt='yuva420p', t=dur, r=fps).overwrite_output().run()
        video_paths.append(out_path)

    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, 'w') as f:
        for p in video_paths:
            f.write(f"file '{p}'\n")

    ffmpeg.input(concat_file, format='concat', safe=0).output(output_path, c='copy').overwrite_output().run()
    return output_path

def api_text_to_video(script_input, duration_input, fps, width, height):
    try:
        scripts = json.loads(script_input)
        durations = json.loads(duration_input)
        if len(scripts) != len(durations):
            return None, "❌ Scripts và durations không khớp!"
        out_path = "outputs/video_from_text.mp4"
        video_path = text_to_video(scripts, durations, out_path, fps, width, height)
        return video_path, "✅ Video chữ đã tạo thành công!"
    except Exception as e:
        return None, f"❌ Lỗi: {str(e)}"

text_to_video_tab = gr.Interface(
    fn=api_text_to_video,
    inputs=[
        gr.Textbox(label="Scripts", placeholder="['Xin chào', 'Đây là ví dụ']"),
        gr.Textbox(label="Durations", placeholder="[3, 4]"),
        gr.Slider(minimum=1, maximum=120, step=1, label="FPS", value=30),
        gr.Number(label="Width", value=1280),
        gr.Number(label="Height", value=720),
    ],
    outputs=[
        gr.Video(label="Video chữ"),
        gr.Textbox(label="Trạng thái"),
    ],
    title="API 2 - Tạo video chữ (nền trong suốt)",
)

### ============================
### API 3: Ghép 2 video
### ============================

def merge_two_videos(video1, video2):
    out_path = "outputs/merged_video.mp4"
    input1 = ffmpeg.input(video1.name)
    input2 = ffmpeg.input(video2.name)
    (
        ffmpeg.concat(input1, input2, v=1, a=1)
        .output(out_path)
        .overwrite_output()
        .run()
    )
    return out_path, "✅ Video đã ghép thành công!"

merge_video_tab = gr.Interface(
    fn=merge_two_videos,
    inputs=[
        gr.File(file_types=["video"], label="Video 1"),
        gr.File(file_types=["video"], label="Video 2"),
    ],
    outputs=[
        gr.Video(label="Video ghép"),
        gr.Textbox(label="Trạng thái")
    ],
    title="API 3 - Ghép 2 video",
)

### ============================
### Giao diện chính
### ============================

demo = gr.TabbedInterface(
    interface_list=[
        image_to_video_tab,
        text_to_video_tab,
        merge_video_tab
    ],
    tab_names=["Tạo video từ ảnh", "Tạo video từ chữ", "Ghép 2 video"]
)

if __name__ == "__main__":
    demo.queue().launch()
