import os
import ffmpeg
import tempfile
import json
import numpy as np
from PIL import Image
import gradio as gr
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import subprocess

# Thiết lập ffmpeg path
os.environ["PATH"] += os.pathsep + r"D:\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"
os.makedirs("outputs", exist_ok=True)

TIMEOUT = 300  # 5 phút

### ============================
### API 1: Ảnh + nhạc => video (giữ nguyên)
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

from PIL import ImageFont

def wrap_text(text, max_width, font_path, font_size=20):
    print("shdhjsadghjsgdjhsgjhd ", max_width)
    font = ImageFont.truetype(font_path, font_size)
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = current_line + " " + word if current_line else word
        line_width, _ = font.getsize(test_line)
        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return "\n".join(lines)

def calculate_text_height(text, font_size=20, line_spacing=10):
    lines = text.split("\n")
    return len(lines) * font_size + (len(lines) - 1) * line_spacing

# def overlay_subtitles_stickers_audio(video_path, scripts, stickers, audio_path, audio_duration, output_path, width=592, height=800):
#     try:
#         font_regular = "fonts/Roboto-VariableFont_wdth_wght.ttf"
#         font_bold = "fonts/Roboto_Condensed-Bold.ttf"
#         font_bold_italic = "fonts/Roboto_Condensed-BoldItalic.ttf"
#         filter_complex = []
#         inputs = [video_path]
#         audio_filters = []

#         # Xử lý phụ đề
#         for i, script in enumerate(scripts):
#             text = script.get("text", "")
#             duration = script.get("duration", 1)
#             start = script.get("start", sum(s.get("duration", 0) for s in scripts[:i]))
#             end = start + duration

#             style = script.get("style", {})
#             position = style.get("position", "bottom")
#             font_size = style.get("fontSize", 20)
#             font_color = style.get("fontColor", "white")
#             bg_color = style.get("backgroundColor", "black@0.5")
#             font_style = style.get("fontStyle", [])
#             alignment = style.get("alignment", "center")
#             shadow = style.get("shadow", {})
#             outline = style.get("outline", {})
#             width_text = style.get("width", width)

#             # Chọn font
#             if "bold" in font_style and "italic" in font_style:
#                 font_path = font_bold_italic
#             elif "bold" in font_style:
#                 font_path = font_bold
#             else:
#                 font_path = font_regular

#             wrapped = wrap_text(text, width_text, font_path, font_size)
#             wrapped = wrapped.replace(":", "\\:").replace("'", "\\'")

#             if position == "top":
#                 y = 30
#             elif position == "middle":
#                 y = "(h-text_h)/2"
#             else:  # bottom
#                 y = "h-text_h-30"

#             x = "(w-text_w)/2" if alignment == "center" else "10" if alignment == "left" else "w-text_w-10"

#             shadow_str = ""
#             if shadow:
#                 shadow_color = shadow.get("color", "black")
#                 shadow_x = shadow.get("offsetX", 2)
#                 shadow_y = shadow.get("offsetY", 2)
#                 shadow_str = f":shadowcolor={shadow_color}:shadowx={shadow_x}:shadowy={shadow_y}"

#             outline_str = ""
#             if outline:
#                 outline_color = outline.get("color", "black")
#                 outline_width = outline.get("width", 2)
#                 outline_str = f":bordercolor={outline_color}:borderw={outline_width}"

#             filter_complex.append(
#                 f"drawtext=text='{wrapped}':fontsize={font_size}:fontcolor={font_color}:x={x}:y={y}:"
#                 f"fontfile='{font_path}':box=1:boxcolor={bg_color}:boxborderw=10:line_spacing=10:"
#                 f"enable='between(t,{start},{end})'{shadow_str}{outline_str}"
#             )

#         # Xử lý nhãn dán
#         for i, sticker in enumerate(stickers):
#             sticker_path = sticker.get("file_path")
#             print("Nhãn dán được thêm: ", sticker_path)
#             if not os.path.exists(sticker_path):
#                 return f"❌ File nhãn dán {sticker_path} không tồn tại!"

#             duration = sticker.get("duration", 1)
#             start = sticker.get("start", sum(s.get("duration", 0) for s in stickers[:i]))
#             end = start + duration
#             sticker_width = sticker.get("width", 100)
#             sticker_height = sticker.get("height", 100)
#             position = sticker.get("position", {"x": 0, "y": 0})
#             rotate = sticker.get("rotate", 0)

#             x = position.get("x", 0)
#             y = position.get("y", 0)

#             inputs.append(sticker_path)
#             input_idx = len(inputs) - 1

#             scale_filter = f"scale={sticker_width}:{sticker_height}"
#             if rotate:
#                 scale_filter += f",rotate={rotate}*PI/180"

#             filter_complex.append(
#                 f"[{input_idx}:v]{scale_filter}[sticker_{i}];"
#                 f"[0:v][sticker_{i}]overlay={x}:{y}:enable='between(t,{start},{end})'"
#             )

#         # Xử lý audio
#         if audio_path:
#             inputs.append(audio_path)
#             audio_input_idx = len(inputs) - 1
#             if audio_duration:
#                 audio_filters.append(f"[{audio_input_idx}:a]atrim=duration={audio_duration}[audio]")
#             else:
#                 audio_filters.append(f"[{audio_input_idx}:a]anull[audio]")

#         filter_complex_str = ",".join(filter_complex) if filter_complex else ""

#         command = [
#             "ffmpeg",
#             "-y",
#         ]
#         for input_file in inputs:
#             command += ["-i", input_file]

#         command += [
#             "-filter_complex", filter_complex_str + ";" + ";".join(audio_filters) if audio_filters else filter_complex_str,
#             "-c:v", "libx264",
#             "-pix_fmt", "yuv420p",
#             "-crf", "20",
#             "-preset", "veryfast",
#         ]

#         # Xử lý audio output
#         probe = ffmpeg.probe(video_path)
#         has_video_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])

#         if audio_path:
#             if has_video_audio:
#                 # Mix audio gốc của video và audio mới
#                 command += ["-map", "0:v", "-map", "[audio]", "-c:a", "aac", "-shortest"]
#             else:
#                 command += ["-map", "0:v", "-map", "[audio]", "-c:a", "aac"]
#                 if audio_duration:
#                     command += ["-t", str(audio_duration)]
#         else:
#             if has_video_audio:
#                 command += ["-c:a", "aac", "-shortest"]
#             else:
#                 command += ["-an"]

#         command += [output_path]

#         print("Running command:", " ".join(command))
#         result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
#         print("FFmpeg output:", result.stdout)
#         print("FFmpeg error (if any):", result.stderr)

#         return output_path
#     except subprocess.CalledProcessError as e:
#         return f"❌ FFmpeg failed: {e.stderr}"
#     except Exception as e:
#         import traceback
#         return f"❌ Lỗi khác: {traceback.format_exc()}"

def overlay_subtitles_stickers_audio(video_path, scripts, stickers, audio_path, audio_duration, output_path, width=592, height=800):
    try:
        font_regular = "fonts/Roboto-VariableFont_wdth_wght.ttf"
        font_bold = "fonts/Roboto_Condensed-Bold.ttf"
        font_bold_italic = "fonts/Roboto_Condensed-BoldItalic.ttf"
        filter_complex = []
        inputs = [video_path]
        audio_filters = []

        # 1. Xử lý phụ đề (ghép chữ trước)
        drawtext_filters = []
        current_video_stream = "[0:v]"  # Luồng video chính ban đầu
        for i, script in enumerate(scripts):
            text = script.get("text", "")
            duration = script.get("duration", 1)
            start = script.get("start", sum(s.get("duration", 0) for s in scripts[:i]))
            end = start + duration

            style = script.get("style", {})
            position = style.get("position", "bottom")
            font_size = style.get("fontSize", 20)
            font_color = style.get("fontColor", "white")
            bg_color = style.get("backgroundColor", "black@0.5")
            font_style = style.get("fontStyle", [])
            alignment = style.get("alignment", "center")
            shadow = style.get("shadow", {})
            outline = style.get("outline", {})
            width_text = style.get("width", width)

            # Chọn font
            if "bold" in font_style and "italic" in font_style:
                font_path = font_bold_italic
            elif "bold" in font_style:
                font_path = font_bold
            else:
                font_path = font_regular

            wrapped = wrap_text(text, width_text, font_path, font_size)
            wrapped = wrapped.replace(":", "\\:").replace("'", "\\'")

            if position == "top":
                y = 30
            elif position == "middle":
                y = "(h-text_h)/2"
            else:  # bottom
                y = "h-text_h-30"

            x = "(w-text_w)/2" if alignment == "center" else "10" if alignment == "left" else "w-text_w-10"

            shadow_str = ""
            if shadow:
                shadow_color = shadow.get("color", "black")
                shadow_x = shadow.get("offsetX", 2)
                shadow_y = shadow.get("offsetY", 2)
                shadow_str = f":shadowcolor={shadow_color}:shadowx={shadow_x}:shadowy={shadow_y}"

            outline_str = ""
            if outline:
                outline_color = outline.get("color", "black")
                outline_width = outline.get("width", 2)
                outline_str = f":bordercolor={outline_color}:borderw={outline_width}"

            drawtext_filters.append(
                f"{current_video_stream}drawtext=text='{wrapped}':fontsize={font_size}:fontcolor={font_color}:x={x}:y={y}:"
                f"fontfile='{font_path}':box=1:boxcolor={bg_color}:boxborderw=10:line_spacing=10:"
                f"enable='between(t,{start},{end})'{shadow_str}{outline_str}[v{i}]"
            )
            current_video_stream = f"[v{i}]"  # Cập nhật luồng video sau mỗi drawtext

        # Gộp các bộ lọc drawtext
        if drawtext_filters:
            filter_complex.append(";".join(drawtext_filters))
            current_video_stream = f"[v{len(scripts)-1}]"  # Luồng video sau khi áp dụng tất cả drawtext
        else:
            current_video_stream = "[0:v]"

        # 2. Xử lý nhãn dán (sticker sau)
        for i, sticker in enumerate(stickers):
            sticker_path = sticker.get("file_path")
            print("Nhãn dán được thêm: ", sticker_path)
            if not os.path.exists(sticker_path):
                return f"❌ File nhãn dán {sticker_path} không tồn tại!"

            duration = sticker.get("duration", 1)
            start = sticker.get("start", sum(s.get("duration", 0) for s in stickers[:i]))
            end = start + duration
            sticker_width = sticker.get("width", 100)
            sticker_height = sticker.get("height", 100)
            position = sticker.get("position", {"x": 0, "y": 0})
            rotate = sticker.get("rotate", 0)

            x = position.get("x", 0)
            y = position.get("y", 0)

            inputs.append(sticker_path)
            input_idx = len(inputs) - 1

            scale_filter = f"scale={sticker_width}:{sticker_height}"
            if rotate:
                scale_filter += f",rotate={rotate}*PI/180"

            filter_complex.append(
                f"[{input_idx}:v]{scale_filter}[sticker_{i}];"
                f"{current_video_stream}[sticker_{i}]overlay={x}:{y}:enable='between(t,{start},{end})'[v_s{i}]"
            )
            current_video_stream = f"[v_s{i}]"  # Cập nhật luồng video sau mỗi overlay

        # 3. Xử lý âm thanh (nhạc sau)
        if audio_path:
            inputs.append(audio_path)
            audio_input_idx = len(inputs) - 1
            if audio_duration:
                audio_filters.append(f"[{audio_input_idx}:a]atrim=duration={audio_duration}[audio]")
            else:
                audio_filters.append(f"[{audio_input_idx}:a]anull[audio]")

        # Tạo chuỗi filter_complex
        filter_complex_str = ";".join(filter_complex) if filter_complex else ""

        # Tạo lệnh FFmpeg
        command = [
            "ffmpeg",
            "-y",
        ]
        for input_file in inputs:
            command += ["-i", input_file]

        command += [
            "-filter_complex", filter_complex_str + ";" + ";".join(audio_filters) if audio_filters else filter_complex_str,
            "-map", f"{current_video_stream}",  # Ánh xạ luồng video cuối cùng
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "veryfast",
        ]

        # Xử lý audio output
        probe = ffmpeg.probe(video_path)
        has_video_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])

        if audio_path:
            if has_video_audio:
                # Mix audio gốc của video và audio mới
                command += ["-map", "[audio]", "-c:a", "aac", "-shortest"]
            else:
                command += ["-map", "[audio]", "-c:a", "aac"]
                if audio_duration:
                    command += ["-t", str(audio_duration)]
        else:
            if has_video_audio:
                command += ["-c:a", "aac", "-shortest"]
            else:
                command += ["-an"]

        command += [output_path]

        print("Running command:", " ".join(command))
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        print("FFmpeg output:", result.stdout)
        print("FFmpeg error (if any):", result.stderr)

        return output_path
    except subprocess.CalledProcessError as e:
        return f"❌ FFmpeg failed: {e.stderr}"
    except Exception as e:
        import traceback
        return f"❌ Lỗi khác: {traceback.format_exc()}"

def generate_video_2(video_file, script_input, sticker_files, sticker_config, audio_file, audio_duration):
    try:
        scripts = json.loads(script_input)
        stickers = json.loads(sticker_config) if sticker_config else []
    except Exception as e:
        return None, f"❌ Lỗi khi phân tích đầu vào:\n{e}"

    if sticker_files and len(sticker_files) != len(stickers):
        return None, "❌ Số lượng file nhãn dán và cấu hình nhãn dán phải bằng nhau!"

    try:
        audio_duration = float(audio_duration) if audio_duration else None
    except Exception as e:
        return None, f"❌ Lỗi khi phân tích audio duration:\n{e}"

    try:
        os.makedirs("outputs", exist_ok=True)
        video_path = video_file.name
        audio_path = audio_file.name if audio_file else None

        # Gán file_path cho stickers
        for i, sticker in enumerate(stickers):
            if i < len(sticker_files):
                sticker["file_path"] = sticker_files[i].name
            else:
                return None, f"❌ Thiếu file nhãn dán cho cấu hình {i+1}"

        output_video_path = os.path.join("outputs", "video_with_subtitles.mp4")

        probe = ffmpeg.probe(video_path)
        video_stream = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        result = overlay_subtitles_stickers_audio(video_path, scripts, stickers, audio_path, audio_duration, output_video_path, width, height)
        if isinstance(result, str) and result.startswith("❌"):
            return None, result
        return result, "✅ Video với phụ đề, nhãn dán và nhạc tạo thành công!"
    except Exception as e:
        import traceback
        return None, f"❌ Lỗi khi tạo video:\n{traceback.format_exc()}"
    

text_to_video_tab = gr.Interface(
    fn=generate_video_2,
    inputs=[
        gr.File(file_types=["video"], label="Video chính"),
        gr.Textbox(label="Scripts", placeholder='[{"text": "Xin chào", "duration": 3, "style": {"position": "bottom", "fontSize": 20, "fontColor": "white", "backgroundColor": "black@0.5", "fontStyle": ["bold"], "alignment": "center", "shadow": {"color": "black", "offsetX": 2, "offsetY": 2}, "outline": {"color": "red", "width": 2}}}]'),
        gr.File(file_types=["image"], label="Nhãn dán", file_count="multiple"),
        gr.Textbox(label="Stickers Config", placeholder='[{"duration": 3, "start": 0, "width": 100, "height": 100, "position": {"x": 50, "y": 50}, "rotate": 45}]'),
        gr.File(file_types=["audio"], label="Nhạc nền"),
        gr.Textbox(label="Audio Duration (giây)", placeholder="Nhập thời gian nhạc (ví dụ: 10) hoặc để trống"),
    ],
    outputs=[
        gr.Video(label="Video với phụ đề, nhãn dán và nhạc"),
        gr.Textbox(label="Trạng thái"),
    ],
    title="API 2 - Chèn phụ đề, nhãn dán và nhạc vào video",
)

### ============================
### Giao diện chính
### ============================

demo = gr.TabbedInterface(
    interface_list=[
        image_to_video_tab,
        text_to_video_tab
    ],
    tab_names=["Tạo video từ ảnh", "Tạo video từ chữ"]
)

if __name__ == "__main__":
    demo.queue().launch()