from huggingface_hub import hf_hub_download
import shutil
import os

repo_id = "Comfy-Org/z_image_turbo"
filename = "split_files/diffusion_models/z_image_turbo_bf16.safetensors"
local_dir = "D:/Projects/ComfyUI/models/checkpoints"

print(f"Downloading {filename} from {repo_id}...")
# Force download to local dir, not cache (symlinks=False)
file_path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=local_dir, local_dir_use_symlinks=False)

# The file will be at D:/Projects/ComfyUI/models/checkpoints/split_files/diffusion_models/z_image_turbo_bf16.safetensors
# We want it at D:/Projects/ComfyUI/models/checkpoints/z-image-turbo.safetensors

target_path = os.path.join(local_dir, "z-image-turbo.safetensors")
if os.path.exists(file_path):
    print(f"Moving to {target_path}...")
    if os.path.exists(target_path):
        os.remove(target_path)
    os.rename(file_path, target_path)
    
    # Cleanup empty directories
    try:
        os.rmdir(os.path.dirname(file_path)) # split_files/diffusion_models
        os.rmdir(os.path.dirname(os.path.dirname(file_path))) # split_files
    except:
        pass
    print("Done!")
