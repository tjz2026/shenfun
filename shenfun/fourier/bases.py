import numpy as np
import pyfftw
from shenfun.spectralbase import SpectralBase
from shenfun.utilities import inheritdocstrings

__all__ = ['FourierBase', 'R2CBasis', 'C2CBasis']


@inheritdocstrings
class FourierBase(SpectralBase):
    """Fourier base class

    A basis function phi_k is given as

        phi_k(x) = exp(ikx)

    and an expansion is given as

        u(x) = \sum_k \hat{u}_k exp(ikx)                            (1)

    where
        k  -N/2, -N/2+1, ..., N/2-1

    However, since exp(ikx) = exp(i(k \pm N)x) this expansion can also be
    written as an interpolator

        u(x) = \sum_k \hat{u}_k/c_k exp(ikx)                        (2)

    where

        k  -N/2, -N/2+1, ..., N/2-1, N/2

    and c_{N/2} = c_{-N/2} = 2, whereas c_k = 1 for k=-N/2+1, ..., N/2-1

    The interpolator form is used for computing odd derivatives. Otherwise,
    it makes no difference and therefore (1) is used in transforms, since
    this is the form expected by pyfftw.

    args:
        N                int    Number of quadrature points. Should be even
                                for efficiency, but this is not required.

    kwargs:
        padding_factor  float   Factor for padding backward transforms.
                                padding_factor=1.5 corresponds to a 3/2-rule
                                for dealiasing.
        domain    (start, stop) Tuple describing the domain.
        dealias_direct   bool   True for dealiasing using 2/3-rule. Must be
                                used with padding_factor == 1.

    """

    def __init__(self, N, padding_factor=1., domain=(0, 2*np.pi),
                 dealias_direct=False):
        self.dealias_direct = dealias_direct
        SpectralBase.__init__(self, N, '', padding_factor, domain)

    def points_and_weights(self, N, scaled=False):
        """Return points and weights of quadrature

        """
        a, b = self.domain
        points = np.arange(N, dtype=np.float)*2*np.pi/N
        if scaled is True:
            points = points*(b-a)/(2*np.pi) + a
        return points, np.array([2*np.pi/N])

    def vandermonde(self, x):
        """Return Vandermonde matrix

        args:
            x               points for evaluation

        """
        k = self.wavenumbers(self.N, 0)
        return np.exp(1j*x[:, np.newaxis]*k[np.newaxis, :])

    def get_vandermonde_basis_derivative(self, V, d=0):
        """Return d'th derivative of basis as a Vandermonde matrix

        args:
            V               Chebyshev Vandermonde matrix

        kwargs:
            d    integer    d'th derivative

        """
        if d > 0:
            k = self.wavenumbers(self.N, 0, True)
            V = V*((1j*k)**d)[np.newaxis, :]
        return V

    def get_mass_matrix(self):
        from .matrices import mat
        return mat[(self.__class__, 0), (self.__class__, 0)]

    def _get_mat(self):
        from .matrices import mat
        return mat

    def domain_factor(self):
        a, b = self.domain
        if (b-a) == 2.*np.pi:
            return 1
        else:
            return 2.*np.pi/(b-a)

    # Note. forward is reimplemented here to avoid one array scaling (scalar_product multiplies with 2pi/N, whereas apply_inverse_mass divides by 2pi)
    def forward(self, input_array=None, output_array=None, fast_transform=True):
        """Forward transform

        kwargs:
            input_array    (input)     Function values on quadrature mesh
            output_array   (output)    Expansion coefficients
            fast_transform   bool      If True use fast transforms, if False
                                       use Vandermonde type

        If kwargs input_array/output_array are not given, then use predefined
        arrays as planned with self.plan

        """
        if fast_transform is False:
            return SpectralBase.forward(self, input_array, output_array, False)

        if input_array is not None:
            self.forward.input_array[...] = input_array

        output = self.xfftn_fwd()
        self._truncation_forward(self.xfftn_fwd.output_array,
                                 self.forward.output_array)
        self.forward._output_array *= (1./self.N/self.padding_factor)

        if output_array is not None:
            output_array[...] = self.forward.output_array
            return output_array
        else:
            return self.forward.output_array

    def apply_inverse_mass(self, array):
        """Apply inverse mass, which is 2pi*identity for Fourier basis

        args:
            array   (input/output)    Expansion coefficients

        """
        array *= (1./(2.*np.pi))
        return array

    def evaluate_expansion_all(self, input_array, output_array):
        self.xfftn_bck(normalise_idft=False)
        return output_array

    def scalar_product(self, input_array=None, output_array=None, fast_transform=True):
        if input_array is not None:
            self.xfftn_fwd.input_array[...] = input_array

        if fast_transform:
            output = self.xfftn_fwd()
            output *= (2*np.pi/self.N/self.padding_factor)

        else:
            assert abs(self.padding_factor-1) < 1e-8
            self.vandermonde_scalar_product(self.xfftn_fwd.input_array,
                                            self.xfftn_fwd.output_array)

        if output_array is not None:
            output_array[...] = self.xfftn_fwd.output_array
            return output_array
        else:
            return self.xfftn_fwd.output_array


class R2CBasis(FourierBase):
    """Fourier basis class for real to complex transforms
    """

    def __init__(self, N, padding_factor=1., plan=False, domain=(0., 2.*np.pi),
                 dealias_direct=False):
        FourierBase.__init__(self, N, padding_factor, domain, dealias_direct)
        self.N = N
        self._xfftn_fwd = pyfftw.builders.rfft
        self._xfftn_bck = pyfftw.builders.irfft
        if plan:
            self.plan((int(np.floor(padding_factor*N)),), 0, np.float, {})

    def wavenumbers(self, N, axis=0, scaled=False, eliminate_highest_freq=False):
        """Return the wavenumbermesh

        All dimensions, except axis, are obtained through broadcasting.

        """
        N = list(N) if np.ndim(N) else [N]
        assert self.N == N[axis]
        k = np.fft.rfftfreq(N[axis], 1./N[axis])
        if N[axis] % 2 == 0 and eliminate_highest_freq:
            k[-1] = 0
        if scaled:
            a, b = self.domain
            k *= 2.*np.pi/(b-a)
        K = self.broadcast_to_ndims(k, len(N), axis)
        return K

    def _get_truncarray(self, shape, dtype):
        shape = list(shape)
        shape[self.axis] = int(shape[self.axis] / self.padding_factor)
        shape[self.axis] = shape[self.axis]//2 + 1
        return pyfftw.empty_aligned(shape, dtype=dtype)

    def eval(self, x, fk):
        V = self.vandermonde(x)
        return np.dot(V, fk) + np.conj(np.dot(V[:, 1:-1], fk[1:-1]))

    def slice(self):
        return slice(0, self.N//2+1)

    def vandermonde_evaluate_expansion_all(self, input_array, output_array):
        """Naive implementation of evaluate_expansion_all

        args:
            input_array    (input)    Expansion coefficients
            output_array   (output)   Function values on quadrature mesh

        """
        assert abs(self.padding_factor-1) < 1e-8
        assert self.N == output_array.shape[self.axis]
        points = self.points_and_weights(self.N)[0]
        P = self.vandermonde(points)
        if output_array.ndim == 1:
            output_array[:] = np.dot(P, input_array).real
            if self.N % 2 == 0:
                output_array += np.conj(np.dot(P[:, 1:-1], input_array[1:-1])).real
            else:
                output_array += np.conj(np.dot(P[:, 1:], input_array[1:])).real

        else:
            fc = np.moveaxis(input_array, self.axis, -2)
            array = np.dot(P, fc).real
            s = [slice(None)]*fc.ndim
            if self.N % 2 == 0:
                s[-2] = slice(1, -1)
                array += np.conj(np.dot(P[:, 1:-1], fc[s])).real
            else:
               s[-2] = slice(1, None)
               array += np.conj(np.dot(P[:, 1:], fc[s])).real

            output_array[:] = np.moveaxis(array, 0, self.axis)

        return output_array

    def _truncation_forward(self, padded_array, trunc_array):
        if self.padding_factor > 1.0+1e-8:
            trunc_array.fill(0)
            N = trunc_array.shape[self.axis]
            s = [slice(None)]*trunc_array.ndim
            s[self.axis] = slice(0, N)
            trunc_array[:] = padded_array[s]
            if self.N % 2 == 0:
                s[self.axis] = N-1
                trunc_array[s] = trunc_array[s].real

    def _padding_backward(self, trunc_array, padded_array):
        if self.padding_factor > 1.0+1e-8:
            padded_array.fill(0)
            N = trunc_array.shape[self.axis]
            s = [slice(0, n) for n in trunc_array.shape]
            padded_array[s] = trunc_array[s]
            if self.N % 2 == 0:
                s[self.axis] = self.N//2
                padded_array[s] = padded_array[s].real

        elif self.dealias_direct:
            N = self.N
            su = [slice(None)]*padded_array.ndim
            su[self.axis] = slice(int(np.floor(N/3.)), None)
            padded_array[su] = 0


class C2CBasis(FourierBase):
    """Fourier basis class for complex to complex transforms
    """

    def __init__(self, N, padding_factor=1., plan=False, domain=(0., 2.*np.pi),
                 dealias_direct=False):
        FourierBase.__init__(self, N, padding_factor, domain, dealias_direct)
        self.N = N
        self._xfftn_fwd = pyfftw.builders.fft
        self._xfftn_bck = pyfftw.builders.ifft
        if plan:
            self.plan((int(np.floor(padding_factor*N)),), 0, np.complex, {})

    def wavenumbers(self, N, axis=0, scaled=False, eliminate_highest_freq=False):
        """Return the wavenumbermesh

        All dimensions, except axis, are obtained through broadcasting.

        """
        N = list(N) if np.ndim(N) else [N]
        assert self.N == N[axis]
        k = np.fft.fftfreq(N[axis], 1./N[axis])
        if N[axis] % 2 == 0 and eliminate_highest_freq:
            k[N[axis]//2] = 0
        if scaled:
            a, b = self.domain
            k *= 2.*np.pi/(b-a)
        K = self.broadcast_to_ndims(k, len(N), axis)
        return K

    def eval(self, x, fk):
        V = self.vandermonde(x)
        return np.dot(V, fk)

    def slice(self):
        return slice(0, self.N)

    def vandermonde_evaluate_expansion_all(self, input_array, output_array):
        """Naive implementation of evaluate_expansion_all

        args:
            input_array    (input)    Expansion coefficients
            output_array   (output)   Function values on quadrature mesh

        """
        assert abs(self.padding_factor-1) < 1e-8
        assert self.N == output_array.shape[self.axis]
        points = self.points_and_weights(self.N)[0]
        V = self.vandermonde(points)
        P = self.get_vandermonde_basis(V)
        if output_array.ndim == 1:
            output_array = np.dot(P, input_array, out=output_array)
        else:
            fc = np.moveaxis(input_array, self.axis, -2)
            array = np.dot(P, fc)
            output_array[:] = np.moveaxis(array, 0, self.axis)

        assert output_array is self.backward.output_array
        assert input_array is self.backward.input_array
        return output_array

    def _truncation_forward(self, padded_array, trunc_array):
        if self.padding_factor > 1.0+1e-8:
            trunc_array.fill(0)
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*trunc_array.ndim
            su[self.axis] = slice(0, N//2+1)
            trunc_array[su] = padded_array[su]
            su[self.axis] = slice(-(N//2), None)
            trunc_array[su] += padded_array[su]

    def _padding_backward(self, trunc_array, padded_array):
        if self.padding_factor > 1.0+1e-8:
            padded_array.fill(0)
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*trunc_array.ndim
            su[self.axis] = slice(0, np.ceil(N/2.).astype(np.int))
            padded_array[su] = trunc_array[su]
            su[self.axis] = slice(-(N//2), None)
            padded_array[su] = trunc_array[su]

        elif self.dealias_direct:
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*padded_array.ndim
            su[self.axis] = slice(int(np.floor(N/3.)), int(np.floor(2./3.*N)))
            padded_array[su] = 0


def FourierBasis(N, dtype, padding_factor=1., plan=False, domain=(0., 2.*np.pi),
                 dealias_direct=False):
    """Fourier basis"""
    dtype = np.dtype(dtype)
    if dtype.char in 'fdg':
        return R2CBasis(N, padding_factor, plan, domain, dealias_direct)

    else:
        return C2CBasis(N, padding_factor, plan, domain, dealias_direct)
