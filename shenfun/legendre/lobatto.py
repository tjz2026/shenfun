import numpy as np
from numpy.polynomial import legendre as leg

def legendre_lobatto_nodes_and_weights(N):
    M = N//2
    j = np.arange(1, M)
    x = np.zeros(N)
    x[0] = -1.
    x[-1] = 1.

    x[1:M] = -np.cos((j+0.25)*np.pi/N - 3./(8.*N*np.pi*(j+0.25)))
    Ln = leg.Legendre.basis(N-1)
    Ld = Ln.deriv(1)
    Ld2 = Ln.deriv(2)
    converged = False
    dx = np.zeros_like(x[1:M])
    y = x[1:M]
    count = 0
    while not converged and count < 10:
        dx[:] = Ld(y)/Ld2(y)
        y -= dx
        error = np.linalg.norm(dx)
        converged = error < 1e-16
        count += 1
        #print(count, error)

    MM = M if N % 2 == 0 else M+1
    x[MM:-1] = -x[1:M][::-1]
    w = 2./(N*(N-1)*Ln(x)**2)
    return x, w


def legendre_gauss_nodes_and_weights(N):
    M = N//2
    j = np.arange(1, M)
    x = np.zeros(N)
    s = quadpy.line_segment.GaussLegendre(N)
    x[:] = s.points

    Ln = leg.Legendre.basis(N)
    Ld = Ln.deriv(1)
    converged = False
    dx = np.zeros_like(x)
    count = 0
    while not converged and count < 10:
        dx[:] = Ln(x)/Ld(x)
        x -= dx
        error = np.linalg.norm(dx)
        converged = error < 1e-16
        count += 1
        print(count, error)

    MM = M if N % 2 == 0 else M+1
    x[MM:-1] = -x[1:M][::-1]
    w = 2./(1-x**2)/Ld(x)**2
    return x, w

if __name__ == '__main__': # pragma: no cover
    import sys
    from time import time
    import quadpy

    N = eval(sys.argv[-1])
    t0 = time()
    x, w = legendre_lobatto_nodes_and_weights(N)
    print("Time mine {}".format(time()-t0))

    t0 = time()
    s = quadpy.line_segment.GaussLobatto(N)
    print("Time quadpy {}".format(time()-t0))

    assert np.allclose(x, s.points)
    assert np.allclose(w, s.weights)

    t0 = time()
    x, w = legendre_gauss_nodes_and_weights(N)
    print("Time mine {}".format(time()-t0))

    t0 = time()
    s = quadpy.line_segment.GaussLegendre(N)
    print("Time quadpy {}".format(time()-t0))

    assert np.allclose(x, s.points)
    assert np.allclose(w, s.weights)
