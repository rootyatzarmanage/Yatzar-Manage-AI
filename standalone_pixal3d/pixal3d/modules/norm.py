import torch
import torch.nn as nn
from .utils import manual_cast


class LayerNorm32(nn.LayerNorm):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x_dtype = x.dtype
        if x.ndim >= 2 and x.shape[0] > 65536:
            chunk_size = 65536
            chunks = []
            for start_idx in range(0, x.shape[0], chunk_size):
                end_idx = min(start_idx + chunk_size, x.shape[0])
                chunk_x = manual_cast(x[start_idx:end_idx], torch.float32)
                chunk_o = super().forward(chunk_x)
                chunks.append(manual_cast(chunk_o, x_dtype))
            return torch.cat(chunks, dim=0)

        x = manual_cast(x, torch.float32)
        o = super().forward(x)
        return manual_cast(o, x_dtype)
    

class GroupNorm32(nn.GroupNorm):
    """
    A GroupNorm layer that converts to float32 before the forward pass.
    """
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x_dtype = x.dtype
        x = manual_cast(x, torch.float32)
        o = super().forward(x)
        return manual_cast(o, x_dtype)
    
    
class ChannelLayerNorm32(LayerNorm32):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        DIM = x.dim()
        x = x.permute(0, *range(2, DIM), 1).contiguous()
        x = super().forward(x)
        x = x.permute(0, DIM-1, *range(1, DIM-1)).contiguous()
        return x
    