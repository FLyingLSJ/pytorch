# coding=utf-8
r"""Quantized convolution modules."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np

from torch._jit_internal import weak_module, weak_script_method
from torch._ops import ops
from torch.nn.modules.module import Module
from torch.nn.modules.utils import _pair


"""Computes the output shape given convolution parameters."""
def _conv_output_shape(input_size, kernel_size, padding, stride, dilation,
                       output_padding=0):
    return np.floor((input_size + 2 * padding - kernel_size - (kernel_size - 1)
                    * (dilation - 1)) / stride) + 2 * output_padding + 1

@weak_module
class _ConvNd(Module):
    def __init__(self, weight, bias, scale, zero_point, dtype,
                 stride, padding, dilation, transposed, output_padding,
                 groups, padding_mode):
        if transposed:
            raise NotImplementedError("Transposed convolution not implemented!")
        super(_ConvNd, self).__init__()
        self.in_channels = weight.shape[1] * groups
        self.out_channels = weight.shape[0]
        self.kernel_size = weight.shape[2:]
        self.stride = stride
        self.padding = padding
        self.dilation = dilation
        self.transposed = transposed
        self.output_padding = output_padding
        self.groups = groups
        self.padding_mode = padding_mode

        self._weight = weight  # Store the original weight for future reference.
        self._packed_weight = ops.quantized.fbgemm_conv_prepack(self._weight,
                                                                self.groups)
        self.bias = bias
        self.bias.requires_grad = False  # Inference only!

        self.dtype = dtype
        self.scale = scale
        self.zero_point = zero_point

    @property
    def weight(self):
        return self._packed_weight

    @weight.setter
    def weight(self, w):
        self._weight = w
        self._packed_weight = ops.quantized.fbgemm_conv_prepack(self._weight,
                                                                self.groups)

    @weight.deleter
    def weight(self):
        del self._weight
        del self._packed_weight

    def extra_repr(self):
        s = super(_ConvNd, self).extra_repr()
        s += ', scale={scale}, zero_point={zero_point}, dtype={dtype}'
        return s.format(**self.__dict__)


@weak_module
class Conv2d(_ConvNd):
    def __init__(self, weight, bias, scale, zero_point, dtype,
                 stride=1, padding=0, dilation=1, groups=1,
                 padding_mode='zeros'):
        if padding_mode != 'zeros':
            raise NotImplementedError(
                "Currently only zero-padding is supported!")
        stride = _pair(stride)
        padding = _pair(padding)
        dilation = _pair(dilation)
        transposed = False
        output_padding = 0
        super(Conv2d, self).__init__(weight=weight,
                                     bias=bias,
                                     scale=scale,
                                     zero_point=zero_point,
                                     dtype=dtype,
                                     stride=stride,
                                     padding=padding,
                                     dilation=dilation,
                                     transposed=transposed,
                                     output_padding=output_padding,
                                     groups=groups,
                                     padding_mode=padding_mode)

    @weak_script_method
    def forward(self, input):
        if input.ndim != 4:
            raise ValueError("Input shape must be `(N, C, H, W)`!")
        return ops.quantized.fbgemm_conv2d(input,
                                           self.weight, self.bias,
                                           self.stride, self.padding,
                                           self.dilation, self.groups,
                                           self.scale, self.zero_point)
