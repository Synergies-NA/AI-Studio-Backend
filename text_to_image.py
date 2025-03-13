from diffusers import DiffusionPipeline
import torch
import platform

pipe = DiffusionPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")

if platform.system() != "Darwin":
    # optmization for CUDA, devides with a GPU (Nvidia)
    pipe.to("cuda")
else:
    pipe.to("mps") # optimization for Apple Silicon Mac


# if using torch < 2.0
# pipe.enable_xformers_memory_efficient_attention()

prompt = "An astronaut riding a green horse"

images = pipe(prompt=prompt).images[0]