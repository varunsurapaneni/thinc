try:
    import cupy
    import cupy.cuda
    from cupy.cuda.compiler import compile_with_cache  # noqa: F401

    # We no longer have to set up the memory pool, fortunately.
except ImportError:
    cupy = None


from .base import Ops
from .numpy_ops import NumpyOps
from . import _custom_kernels
from ..util import copy_array, get_array_module


class CupyOps(Ops):
    device = "gpu"
    xp = cupy

    def matmul(self, x, y, out=None):
        return self.xp.matmul(x, y, out=out)

    def gemm(self, x, y, out=None, trans1=False, trans2=False):
        if trans1:
            x = x.T
        if trans2:
            y = y.T
        if out is None:
            return self.xp.dot(x, y)
        else:
            self.xp.dot(x, y, out=out)
            return out

    def asarray(self, X, dtype=None):
        if isinstance(X, cupy.ndarray):
            return self.xp.asarray(X, dtype=dtype)
        elif hasattr(X, "data_ptr"):
            # Handles PyTorch Tensors
            pointer = cupy.cuda.MemoryPointer(X.data_ptr())
            shape = X.stride()
            array = self.xp.ndarray(shape, memptr=pointer, dtype=dtype)
            return array
        else:
            return self.xp.array(X, dtype=dtype)

    def maxout(self, X):
        return _custom_kernels.maxout(X)

    def backprop_maxout(self, dY, which, P):
        return _custom_kernels.backprop_maxout(dY, which, P)

    def relu(self, X, inplace=False):
        if not inplace:
            return X * (X > 0)
        else:
            X *= X > 0
            return X

    def backprop_relu(self, delta_, signal_out, inplace=False):
        if not inplace:
            return delta_ * (signal_out > 0)
        delta_ *= signal_out > 0
        return delta_

    def mish(self, X, threshold=5, out=None):
        return _custom_kernels.mish(X, threshold=threshold, out=out)

    def backprop_mish(self, dY, X, threshold=5, out=None):
        return _custom_kernels.backprop_mish(dY, X, threshold=threshold, out=out)

    def clip_gradient(self, gradient, threshold):
        xp = get_array_module(gradient)
        grad_norm = xp.linalg.norm(gradient)
        if grad_norm >= threshold:
            gradient *= threshold / grad_norm

    def seq2col(self, seq, nW):
        """Given an (M, N) sequence of vectors, return an (M, N*(nW*2+1)) sequence.
        The new sequence is constructed by concatenating nW preceding and succeeding
        vectors onto each column in the sequence, to extract a window of features.
        """
        return _custom_kernels.seq2col(seq, nW)

    def backprop_seq2col(self, dY, nW):
        return _custom_kernels.backprop_seq2col(dY, nW)

    def mean_pool(self, X, lengths):
        return _custom_kernels.mean_pool(X, lengths)

    def backprop_mean_pool(self, d_means, lengths):
        return _custom_kernels.backprop_mean_pool(d_means, lengths)

    def max_pool(self, X, lengths):
        return _custom_kernels.max_pool(X, lengths)

    def backprop_max_pool(self, d_maxes, which, lengths):
        return _custom_kernels.backprop_max_pool(d_maxes, which, lengths)

    def sum_pool(self, X, lengths):
        return _custom_kernels.sum_pool(X, lengths)

    def backprop_sum_pool(self, d_sums, lengths):
        return _custom_kernels.backprop_sum_pool(d_sums, lengths)

    def hash(self, ids, seed):
        return _custom_kernels.hash(ids, seed)

    def scatter_add(self, out, ids, inputs):
        self.xp.scatter_add(out, ids, inputs)

    def adam(
        self, weights, gradient, mom1, mom2, beta1, beta2, eps, learn_rate, mod_rate=1.0
    ):
        cupy.ElementwiseKernel(
            "T grad, T lr, T one_minus_beta1, T one_minus_beta2, T eps",
            "T param, T m, T v",
            """m += one_minus_beta1 * (grad - m);
               v += one_minus_beta2 * (grad * grad - v);
               param -= lr * m / (sqrt(v) + eps);""",
            "adam",
        )(gradient, learn_rate, 1 - beta1, 1 - beta2, eps, weights, mom1, mom2)
        gradient.fill(0)

    def normal_init(self, W, fan_in, inplace=True):
        scale = self.xp.sqrt(1.0 / fan_in)
        inits = self.xp.random.normal(scale=scale, size=int(prod(W.shape)))
        inits = inits.reshape(W.shape)
        if inplace:
            copy_array(W, inits)
            return W
        else:
            return inits

    def position_encode(self, *args, **kwargs):
        positions = NumpyOps().position_encode(*args, **kwargs)
        return self.asarray(positions)