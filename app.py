import os
import ffmpeg
import tempfile
import json
import numpy as np
from PIL import Image
from PIL import ImageFont
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

def overlay_subtitles_stickers_audio(video_path, scripts, stickers, audio_configs, output_path, width=592, height=800):
    try:
        font_regular = "fonts/Roboto-VariableFont_wdth_wght.ttf"
        font_bold = "fonts/Roboto_Condensed-Bold.ttf"
        font_bold_italic = "fonts/Roboto_Condensed-BoldItalic.ttf"
        filter_complex = []
        inputs = [video_path]
        audio_filters = []
        audio_inputs = []

        # Xử lý phụ đề
        drawtext_filters = []
        current_video_stream = "[0:v]"
        for i, script in enumerate(scripts):
            text = script.get("text", "")
            start = script.get("start", 0)  # Thay duration bằng start
            end = script.get("end", 1)      # Thêm end
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

            font_path = (
                font_bold_italic if "bold" in font_style and "italic" in font_style
                else font_bold if "bold" in font_style
                else font_regular
            )

            wrapped = wrap_text(text, width_text, font_path, font_size)
            wrapped = wrapped.replace(":", "\\:").replace("'", "\\'")

            y = 30 if position == "top" else "(h-text_h)/2" if position == "middle" else "h-text_h-30"
            x = "(w-text_w)/2" if alignment == "center" else "10" if alignment == "left" else "w-text_w-10"

            shadow_str = (
                f":shadowcolor={shadow.get('color', 'black')}:shadowx={shadow.get('offsetX', 2)}:shadowy={shadow.get('offsetY', 2)}"
                if shadow else ""
            )
            outline_str = (
                f":bordercolor={outline.get('color', 'black')}:borderw={outline.get('width', 2)}"
                if outline else ""
            )

            drawtext_filters.append(
                f"{current_video_stream}drawtext=text='{wrapped}':fontsize={font_size}:fontcolor={font_color}:x={x}:y={y}:"
                f"fontfile='{font_path}':box=1:boxcolor={bg_color}:boxborderw=10:line_spacing=10:"
                f"enable='between(t,{start},{end})'{shadow_str}{outline_str}[v{i}]"
            )
            current_video_stream = f"[v{i}]"

        if drawtext_filters:
            filter_complex.append(";".join(drawtext_filters))
            current_video_stream = f"[v{len(scripts)-1}]"
        else:
            current_video_stream = "[0:v]"

        # Xử lý nhãn dán
        for i, sticker in enumerate(stickers):
            sticker_path = sticker.get("file_path")
            if not os.path.exists(sticker_path):
                return f"❌ Tệp nhãn dán {sticker_path} không tồn tại!"

            start = sticker.get("start", 0)  # Thay duration bằng start
            end = sticker.get("end", 1)      # Thêm end
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
            current_video_stream = f"[v_s{i}]"

        # Xử lý âm thanh (không thay đổi)
        probe = ffmpeg.probe(video_path)
        has_video_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
        video_duration = float(probe['format']['duration'])

        if audio_configs:
            for i, audio in enumerate(audio_configs):
                audio_path = audio.get("file_path")
                if not audio_path or not os.path.exists(audio_path):
                    return f"❌ Tệp âm thanh {audio_path} không tồn tại!"
                
                try:
                    audio_probe = ffmpeg.probe(audio_path)
                    if not any(stream['codec_type'] == 'audio' for stream in audio_probe['streams']):
                        return f"❌ Tệp {audio_path} không phải tệp âm thanh hợp lệ!"
                    audio_duration = float(audio_probe['format']['duration'])
                except ffmpeg.Error as e:
                    return f"❌ Lỗi khi kiểm tra tệp âm thanh {audio_path}: {e.stderr.decode('utf-8')}"

                start = audio.get("start", 0)
                end = audio.get("end", start + 1)
                volume = audio.get("volume", 1.0)

                if start < 0 or end <= start:
                    return f"❌ Cấu hình âm thanh {i+1} có thời gian không hợp lệ: start={start}, end={end}"
                if end - start > audio_duration:
                    return f"❌ Cấu hình âm thanh {i+1} yêu cầu cắt vượt quá độ dài tệp: {end - start}s > {audio_duration}s"

                inputs.append(audio_path)
                audio_input_idx = len(inputs) - 1
                audio_filters.append(
                    f"[{audio_input_idx}:a]atrim=0:{end-start},adelay={int(start*1000)}|{(int(start*1000))},volume={volume}[audio_{i}]"
                )
                audio_inputs.append(f"[audio_{i}]")

        # Mix audio
        if audio_inputs:
            if has_video_audio:
                audio_filters.append("[0:a]volume=1.0[original_audio]")
                audio_inputs.append("[original_audio]")
            audio_filters.append(
                f"{' '.join(audio_inputs)}amix=inputs={len(audio_inputs)}[mixed];[mixed]apad=pad_dur={video_duration}[audio]"
            )
        elif has_video_audio:
            audio_filters.append("[0:a]anull[audio]")
        else:
            audio_filters.append(f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={video_duration}[audio]")

        # Tạo filter_complex
        filter_complex_parts = []
        if filter_complex:
            filter_complex_parts.append(";".join(filter_complex))
        if audio_filters:
            filter_complex_parts.append(";".join(audio_filters))

        filter_complex_str = ";".join(filter_complex_parts) if filter_complex_parts else ""

        # Xây dựng lệnh FFmpeg
        command = ["ffmpeg", "-y"]
        for input_file in inputs:
            command += ["-i", input_file]

        command += [
            "-filter_complex", filter_complex_str,
            "-map", f"{current_video_stream}",
            "-map", "[audio]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "veryfast",
            "-t", str(video_duration),
            output_path
        ]

        print("Danh sách tệp âm thanh:", [audio.get("file_path") for audio in audio_configs])
        print("Cấu hình âm thanh:", audio_configs)
        print("Lệnh FFmpeg:", " ".join(command))

        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        print("FFmpeg output:", result.stdout)
        print("FFmpeg error (if any):", result.stderr)

        return output_path
    except subprocess.CalledProcessError as e:
        return f"❌ FFmpeg thất bại: {e.stderr}"
    except Exception as e:
        import traceback
        return f"❌ Lỗi khác: {traceback.format_exc()}"
    
def generate_video_2(video_file, script_input, sticker_files, sticker_config, audio_files, audio_config):
    try:
        scripts = json.loads(script_input)
        stickers = json.loads(sticker_config) if sticker_config else []
        audio_configs = json.loads(audio_config) if audio_config else []
    except Exception as e:
        return None, f"❌ Lỗi khi phân tích đầu vào:\n{e}"

    # Chuẩn hóa sticker_files và audio_files thành danh sách
    sticker_files = [sticker_files] if isinstance(sticker_files, dict) else sticker_files or []
    audio_files = [audio_files] if isinstance(audio_files, dict) else audio_files or []

    if sticker_files and len(sticker_files) != len(stickers):
        return None, "❌ Số lượng tệp nhãn dán phải khớp với cấu hình nhãn dán!"

    if audio_files and len(audio_files) != len(audio_configs):
        return None, "❌ Số lượng tệp âm thanh phải khớp với cấu hình âm thanh!"

    try:
        os.makedirs("outputs", exist_ok=True)
        video_path = video_file.name
        output_video_path = os.path.join("outputs", "video_with_subtitles.mp4")

        # Gán file_path cho stickers
        for i, sticker in enumerate(stickers):
            if i < len(sticker_files):
                sticker["file_path"] = sticker_files[i]["path"] if isinstance(sticker_files[i], dict) else sticker_files[i].name
            else:
                return None, f"❌ Thiếu tệp nhãn dán cho cấu hình {i+1}"

        # Gán file_path cho audio configs
        for i, audio in enumerate(audio_configs):
            if i < len(audio_files):
                audio["file_path"] = audio_files[i]["path"] if isinstance(audio_files[i], dict) else audio_files[i].name
            else:
                return None, f"❌ Thiếu tệp âm thanh cho cấu hình {i+1}"

        probe = ffmpeg.probe(video_path)
        video_stream = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        result = overlay_subtitles_stickers_audio(video_path, scripts, stickers, audio_configs, output_video_path, width, height)
        if isinstance(result, str) and result.startswith("❌"):
            return None, result
        return result, "✅ Video với phụ đề, nhãn dán và âm thanh được tạo thành công!"
    except Exception as e:
        import traceback
        return None, f"❌ Lỗi khi tạo video:\n{traceback.format_exc()}"

text_to_video_tab = gr.Interface(
    fn=generate_video_2,
    inputs=[
        gr.File(file_types=["video"], label="Video chính"),
        gr.Textbox(
            label="Scripts",
            placeholder='[{"text": "Xin chào", "start": 0, "end": 3, "style": {"position": "bottom", "fontSize": 20, "fontColor": "white", "backgroundColor": "black@0.5", "fontStyle": ["bold"], "alignment": "center", "shadow": {"color": "black", "offsetX": 2, "offsetY": 2}, "outline": {"color": "red", "width": 2}}}]'
        ),
        gr.File(
            file_types=["image"],
            label="Nhãn dán (Tải lên nhiều tệp hình ảnh làm nhãn dán)",
            file_count="multiple"
        ),
        gr.Textbox(
            label="Cấu hình nhãn dán",
            placeholder='[{"start": 0, "end": 3, "width": 100, "height": 100, "position": {"x": 50, "y": 50}, "rotate": 45}]'
        ),
        gr.File(
            file_types=["audio"],
            label="Tệp âm thanh nền (Tải lên nhiều tệp âm thanh làm nhạc nền)",
            file_count="multiple"
        ),
        gr.Textbox(
            label="Cấu hình âm thanh",
            placeholder='[{"start": 0, "end": 5, "volume": 0.5}, {"start": 5, "end": 10, "volume": 0.3}]'
        ),
    ],
    outputs=[
        gr.Video(label="Video với phụ đề, nhãn dán và âm thanh"),
        gr.Textbox(label="Trạng thái"),
    ],
    title="API 2 - Chèn phụ đề, nhãn dán và nhiều bản âm thanh vào video",
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