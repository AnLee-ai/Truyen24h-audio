import gradio as gr
from src.main import run_chapter_pipeline, app as fastapi_app

def trigger_writing(novel_id):
    if not novel_id:
        return "Vui lòng điền Novel ID!"
    try:
        run_chapter_pipeline(novel_id)
        return "Hoàn thành! Audio đã được gửi lên Telegram."
    except Exception as e:
        return f"Lỗi: {e}"

# Build Gradio UI
with gr.Blocks(title="Truyện 24h Audio Control Panel") as demo:
    gr.Markdown("# 🎙️ Truyện 24h Audio Control Panel")
    gr.Markdown("🟢 Trạng thái hệ thống: Hoạt động 24/24")
    
    with gr.Row():
        novel_id_input = gr.Textbox(label="Nhập Novel ID (Supabase UUID)", placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000")
        
    run_btn = gr.Button("🚀 Chạy viết chương mới & Tạo Audio", variant="primary")
    output = gr.Textbox(label="Kết quả chạy", interactive=False)
    
    run_btn.click(fn=trigger_writing, inputs=novel_id_input, outputs=output)

# Mount FastAPI app onto Gradio
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 7860))
    print(f"[INFO] Starting server on port {port}...")
    uvicorn.run("app:app", host="0.0.0.0", port=port)
