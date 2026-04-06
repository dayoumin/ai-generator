from huggingface_hub import hf_hub_download
import os

REPO_ID = "Comfy-Org/z_image_turbo"
COMFY_MODELS = "D:/Projects/ComfyUI/models"

FILES_TO_DOWNLOAD = [
    ("split_files/diffusion_models/z_image_turbo_bf16.safetensors", "diffusion_models", "z_image_turbo_bf16.safetensors"),
    ("split_files/text_encoders/qwen_3_4b.safetensors", "text_encoders", "qwen_3_4b.safetensors"),
    ("split_files/vae/ae.safetensors", "vae", "ae.safetensors"),
]


def download_and_place(repo_path: str, model_subdir: str, final_name: str):
    target_dir = os.path.join(COMFY_MODELS, model_subdir)
    os.makedirs(target_dir, exist_ok=True)

    print(f"Downloading {repo_path} from {REPO_ID}...")
    downloaded_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=repo_path,
        local_dir=target_dir,
    )

    target_path = os.path.join(target_dir, final_name)
    if os.path.abspath(downloaded_path) != os.path.abspath(target_path):
        print(f"Moving to {target_path}...")
        if os.path.exists(target_path):
            os.remove(target_path)
        os.replace(downloaded_path, target_path)

    print(f"Done: {target_path}")


if __name__ == "__main__":
    for repo_path, model_subdir, final_name in FILES_TO_DOWNLOAD:
        download_and_place(repo_path, model_subdir, final_name)
