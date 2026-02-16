from huggingface_hub import hf_hub_download
import shutil
import os

# Base configuration
base_models_dir = "D:/Projects/ComfyUI/models"
checkpoints_dir = os.path.join(base_models_dir, "checkpoints")
clip_dir = os.path.join(base_models_dir, "clip")
vae_dir = os.path.join(base_models_dir, "vae")

# Ensure directories exist
os.makedirs(checkpoints_dir, exist_ok=True)
os.makedirs(clip_dir, exist_ok=True)
os.makedirs(vae_dir, exist_ok=True)

def download_file(repo_id, filename, target_dir, final_name=None):
    print(f"Downloading {filename} from {repo_id}...")
    try:
        file_path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=target_dir, local_dir_use_symlinks=False)

        if final_name:
            target_path = os.path.join(target_dir, final_name)
            # If the downloaded file is not already at the target path (e.g. if it was in a subdir)
            if os.path.abspath(file_path) != os.path.abspath(target_path):
                print(f"Moving to {target_path}...")
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.rename(file_path, target_path)

                # Cleanup empty directories if the file was in a subdir
                cleanup_dir = os.path.dirname(file_path)
                while cleanup_dir != target_dir:
                    try:
                        os.rmdir(cleanup_dir)
                        cleanup_dir = os.path.dirname(cleanup_dir)
                    except OSError:
                        break
        print(f"Successfully downloaded {final_name or filename}")
    except Exception as e:
        print(f"Error downloading {filename}: {e}")

# 1. Download z-image-turbo (UNet)
download_file(
    repo_id="Comfy-Org/z_image_turbo",
    filename="split_files/diffusion_models/z_image_turbo_bf16.safetensors",
    target_dir=checkpoints_dir,
    final_name="z-image-turbo.safetensors"
)

# 2. Download Qwen 3.4B Text Encoder (Required for Z-Image-Turbo)
download_file(
    repo_id="Comfy-Org/z_image_turbo",
    filename="split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors",
    target_dir=clip_dir,
    final_name="qwen_3_4b.safetensors"
)

# 3. Download VAE (Flux VAE)
download_file(
    repo_id="black-forest-labs/FLUX.1-schnell",
    filename="ae.safetensors",
    target_dir=vae_dir,
    final_name="ae.safetensors"
)

print("All downloads complete!")
