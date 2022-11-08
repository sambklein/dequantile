import numpy as np
import torch
from nflows.utils import torchutils
from torch.nn import functional as F


def get_knots(unnormalized_pdf):
    pdf = F.softmax(unnormalized_pdf, dim=-1)

    knot_places = torch.cumsum(pdf, dim=-1)
    knot_places[..., -1] = 1.0
    knot_places = F.pad(knot_places, pad=(1, 0), mode="constant", value=0.0)
    return knot_places


def linear_spline(
        inputs, unnormalized_pdf, inverse=False, left=0.0, right=1.0, bottom=0.0, top=1.0
):
    """
    Reference:
    > Müller et al., Neural Importance Sampling, arXiv:1808.03856, 2018.
    Taken from nflows package
    https://github.com/bayesiains/nflows
    """

    if inverse:
        inputs = (inputs - bottom) / (top - bottom)
    else:
        inputs = (inputs - left) / (right - left)

    num_bins = unnormalized_pdf.size(-1)

    pdf = F.softmax(unnormalized_pdf, dim=-1)
    cdf = get_knots(unnormalized_pdf)

    if inverse:
        inv_bin_idx = torchutils.searchsorted(cdf, inputs)

        bin_boundaries = (
            torch.linspace(0, 1, num_bins + 1)
                .view([1] * inputs.dim() + [-1])
                .expand(*inputs.shape, -1)
        )

        slopes = (cdf[..., 1:] - cdf[..., :-1]) / (
                bin_boundaries[..., 1:] - bin_boundaries[..., :-1]
        )
        offsets = cdf[..., 1:] - slopes * bin_boundaries[..., 1:]

        inv_bin_idx = inv_bin_idx.unsqueeze(-1)
        input_slopes = slopes.gather(-1, inv_bin_idx)[..., 0]
        input_offsets = offsets.gather(-1, inv_bin_idx)[..., 0]

        outputs = (inputs - input_offsets) / input_slopes
        outputs = torch.clamp(outputs, 0, 1)

        logabsdet = -torch.log(input_slopes)
    else:
        bin_pos = inputs * num_bins

        bin_idx = torch.floor(bin_pos).long()
        bin_idx[bin_idx >= num_bins] = num_bins - 1

        alpha = bin_pos - bin_idx.float()

        input_pdfs = pdf.gather(-1, bin_idx[..., None])[..., 0]

        outputs = cdf.gather(-1, bin_idx[..., None])[..., 0]
        outputs += alpha * input_pdfs
        outputs = torch.clamp(outputs, 0, 1)

        bin_width = 1.0 / num_bins
        logabsdet = torch.log(input_pdfs) - np.log(bin_width)

    if inverse:
        outputs = outputs * (right - left) + left
    else:
        outputs = outputs * (top - bottom) + bottom

    return outputs, logabsdet