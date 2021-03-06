import pytest
from shenfun.chebyshev import bases as cbases
from shenfun.legendre import bases as lbases
from shenfun.fourier import bases as fbases

import shenfun
from shenfun.la import TDMA
from shenfun.spectralbase import inner_product
from scipy.linalg import solve
from sympy import chebyshevt, Symbol, sin, cos, pi, lambdify
import numpy as np
import scipy.sparse.linalg as la
from itertools import product

N = 32
x = Symbol("x")

cBasis = (cbases.Basis,
          cbases.ShenDirichletBasis,
          cbases.ShenNeumannBasis,
          cbases.ShenBiharmonicBasis)

lBasis = (lbases.Basis,
          lbases.ShenDirichletBasis,
          lbases.ShenBiharmonicBasis,
          lbases.ShenNeumannBasis)

cquads = ('GC', 'GL')
lquads = ('LG', 'GL')

all_bases_and_quads = list(product(lBasis, lquads))+list(product(cBasis, cquads))

cbases2 = list(list(i[0]) + [i[1]] for i in product(list(product(cBasis, cBasis)), cquads))
lbases2 = list(list(i[0]) + [i[1]] for i in product(list(product(lBasis, lBasis)), lquads))

@pytest.mark.parametrize('ST,quad', product(cBasis, cquads))
def test_scalarproduct(ST, quad):
    """Test fast scalar product against Vandermonde computed version"""
    ST = ST(N, quad=quad, plan=True)
    points, weights = ST.points_and_weights(N)
    f = x*x+cos(pi*x)
    fl = lambdify(x, f, 'numpy')
    fj = fl(points)
    u0 = np.zeros(N)
    u1 = np.zeros(N)
    u0 = ST.scalar_product(fj, u0, fast_transform=True)
    u1 = ST.scalar_product(fj, u1, fast_transform=False)
    assert np.allclose(u1, u0)

#test_scalarproduct(cbases.ShenDirichletBasis, 'GC')

@pytest.mark.parametrize('ST,quad', all_bases_and_quads)
def test_eval(ST, quad):
    """Test eval agains fast inverse"""
    ST = ST(N, quad=quad, plan=True)
    points, weights = ST.points_and_weights(N)
    fk = np.zeros(N)
    fj = np.random.random(N)
    fk = ST.forward(fj, fk)
    #from IPython import embed; embed()
    fj = ST.backward(fk, fj)
    fk = ST.forward(fj, fk)
    f = ST.eval(points, fk)
    assert np.allclose(fj, f)
    fj = ST.backward(fk, fj, fast_transform=False)
    fk = ST.forward(fj, fk, fast_transform=False)
    f = ST.eval(points, fk)
    assert np.allclose(fj, f)

#test_eval(cbases.ShenDirichletBasis, 'GL')

@pytest.mark.parametrize('test, trial, quad', cbases2+lbases2)
def test_massmatrices(test, trial, quad):
    test = test(N, quad=quad, plan=True)
    trial = trial(N, quad=quad, plan=True)

    f_hat = np.zeros(N)
    fj = np.random.random(N)
    f_hat = trial.forward(fj, f_hat)
    fj = trial.backward(f_hat, fj)

    BBD = inner_product((test, 0), (trial, 0))

    f_hat = trial.forward(fj, f_hat)
    u2 = np.zeros_like(f_hat)
    u2 = BBD.matvec(f_hat, u2)
    u0 = np.zeros(N)
    u0 = test.scalar_product(fj, u0)
    s = test.slice()
    #from IPython import embed; embed()
    assert np.allclose(u0[s], u2[s])

    # Multidimensional version
    fj = fj.repeat(N*N).reshape((N, N, N)) + 1j*fj.repeat(N*N).reshape((N, N, N))
    f_hat = f_hat.repeat(N*N).reshape((N, N, N)) + 1j*f_hat.repeat(N*N).reshape((N, N, N))

    test.plan((N,)*3, 0, np.complex, {})
    u0 = np.zeros((N,)*3, dtype=np.complex)
    u0 = test.scalar_product(fj, u0)
    u2 = np.zeros_like(f_hat)
    u2 = BBD.matvec(f_hat, u2)
    assert np.linalg.norm(u2[s]-u0[s])/(N*N*N) < 1e-12
    del BBD

#test_massmatrices(lBasis[3], lBasis[2], 'LG')

@pytest.mark.parametrize('ST,quad', all_bases_and_quads)
@pytest.mark.parametrize('axis', (0,1,2))
def test_transforms(ST, quad, axis):
    #N = 11
    ST = ST(N, quad=quad, plan=True)
    points, weights = ST.points_and_weights(N)
    fj = np.random.random(N)

    # Project function to space first
    f_hat = np.zeros_like(ST.forward.output_array)
    f_hat = ST.forward(fj, f_hat)
    fj = ST.backward(f_hat, fj)

    # Then check if transformations work as they should
    u0 = np.zeros_like(f_hat)
    u1 = np.zeros(N)
    u0 = ST.forward(fj, u0)
    u1 = ST.backward(u0, u1)
    assert np.allclose(fj, u1)
    u0 = ST.forward(fj, u0)
    u1 = ST.backward(u0, u1)
    assert np.allclose(fj, u1)

    # Multidimensional version
    bc = [np.newaxis,]*3
    bc[axis] = slice(None)
    fj = np.broadcast_to(fj[bc], (N,)*3).copy()

    ST.plan((N,)*3, axis, np.float, {})
    if hasattr(ST, 'bc'):
        ST.bc.set_slices(ST)  # To set Dirichlet boundary conditions

    u00 = np.zeros_like(ST.forward.output_array)
    u11 = np.zeros_like(ST.forward.input_array)
    u00 = ST.forward(fj, u00)
    u11 = ST.backward(u00, u11)
    cc = [0,]*3
    cc[axis] = slice(None)
    assert np.allclose(fj[cc], u11[cc])

#test_transforms(cbases.Basis, 'GL', 1)


@pytest.mark.parametrize('ST,quad', all_bases_and_quads)
@pytest.mark.parametrize('axis', (0,1,2))
def test_axis(ST, quad, axis):
    ST = ST(N, quad=quad, plan=True)
    points, weights = ST.points_and_weights(N)
    f_hat = np.random.random(N)

    B = inner_product((ST, 0), (ST, 0))

    c = np.zeros_like(f_hat)
    c = B.solve(f_hat, c)

    # Multidimensional version
    bc = [np.newaxis,]*3
    bc[axis] = slice(None)
    fk = np.broadcast_to(f_hat[bc], (N,)*3).copy()
    ST.plan((N,)*3, axis, np.float, {})
    if hasattr(ST, 'bc'):
        ST.bc.set_tensor_bcs(ST) # To set Dirichlet boundary conditions on multidimensional array
    ck = np.zeros_like(fk)
    ck = B.solve(fk, ck, axis=axis)
    cc = [0,]*3
    cc[axis] = slice(None)
    assert np.allclose(ck[cc], c)

#test_axis(cbases.ShenDirichletBasis, "GC", 1)

@pytest.mark.parametrize('quad', cquads)
def test_CDDmat(quad):
    M = 128
    SD = cbases.ShenDirichletBasis(M, quad=quad, plan=True)
    u = (1-x**2)*sin(np.pi*6*x)
    dudx = u.diff(x, 1)
    points, weights = SD.points_and_weights(M)

    ul = lambdify(x, u, 'numpy')
    dudx_l = lambdify(x, dudx, 'numpy')
    dudx_j = dudx_l(points)
    uj = ul(points)

    dudx_j = np.zeros(M)
    u_hat = np.zeros(M)
    u_hat = SD.forward(uj, u_hat)
    uj = SD.backward(u_hat, uj)
    u_hat = SD.forward(uj, u_hat)

    uc_hat = np.zeros(M)
    uc_hat = SD.CT.forward(uj, uc_hat)
    du_hat = np.zeros(M)
    dudx_j = SD.CT.fast_derivative(uj, dudx_j)

    Cm = inner_product((SD, 0), (SD, 1))
    B = inner_product((SD, 0), (SD, 0))
    TDMASolver = TDMA(B)

    cs = np.zeros_like(u_hat)
    cs = Cm.matvec(u_hat, cs)

    # Should equal (but not exact so use extra resolution)
    cs2 = np.zeros(M)
    cs2 = SD.scalar_product(dudx_j, cs2)
    s = SD.slice()
    assert np.allclose(cs[s], cs2[s])

    cs = TDMASolver(cs)
    du = np.zeros(M)
    du = SD.backward(cs, du)

    assert np.linalg.norm(du[s]-dudx_j[s])/M < 1e-10

    # Multidimensional version
    u3_hat = u_hat.repeat(4*4).reshape((M, 4, 4)) + 1j*u_hat.repeat(4*4).reshape((M, 4, 4))
    cs = np.zeros_like(u3_hat)
    cs = Cm.matvec(u3_hat, cs)
    cs2 = np.zeros((M, 4, 4), dtype=np.complex)
    du3 = dudx_j.repeat(4*4).reshape((M, 4, 4)) + 1j*dudx_j.repeat(4*4).reshape((M, 4, 4))
    SD.plan((M, 4, 4), 0, np.complex, {})
    cs2 = SD.scalar_product(du3, cs2)

    assert np.allclose(cs[s], cs2[s], 1e-10)

    cs = TDMASolver(cs)
    d3 = np.zeros((M, 4, 4), dtype=np.complex)
    d3 = SD.backward(cs, d3)

    assert np.linalg.norm(du3[s]-d3[s])/(M*16) < 1e-10

#test_CDDmat('GL')

@pytest.mark.parametrize('test,trial', product(cBasis, cBasis))
def test_CXXmat(test, trial):
    test = test(N, plan=True)
    trial = trial(N, plan=True)

    CT = cBasis[0](N, plan=True)

    Cm = inner_product((test, 0), (trial, 1))
    S2 = Cm.trialfunction[0]
    S1 = Cm.testfunction[0]

    fj = np.random.randn(N)
    # project to S2
    f_hat = np.zeros(N)
    f_hat = S2.forward(fj, f_hat)
    fj = S2.backward(f_hat, fj)

    # Check S1.scalar_product(f) equals Cm*S2.forward(f)
    f_hat = S2.forward(fj, f_hat)
    cs = np.zeros_like(f_hat)
    cs = Cm.matvec(f_hat, cs)
    df = np.zeros(N)
    df = CT.fast_derivative(fj, df)
    cs2 = np.zeros(N)
    cs2 = S1.scalar_product(df, cs2)
    s = S1.slice()
    assert np.allclose(cs[s], cs2[s])

    # Multidimensional version
    f_hat = f_hat.repeat(4*4).reshape((N, 4, 4)) + 1j*f_hat.repeat(4*4).reshape((N, 4, 4))
    df = df.repeat(4*4).reshape((N, 4, 4)) + 1j*df.repeat(4*4).reshape((N, 4, 4))
    cs = np.zeros_like(f_hat)
    cs = Cm.matvec(f_hat, cs)
    cs2 = np.zeros((N, 4, 4), dtype=np.complex)
    S1.plan((N, 4, 4), 0, np.complex, {})
    cs2 = S1.scalar_product(df, cs2)

    assert np.allclose(cs[s], cs2[s])

#test_CXXmat(cBasis[2], cBasis[1])

dirichlet_with_quads = (list(product([cbases.ShenNeumannBasis, cbases.ShenDirichletBasis], cquads)) +
                        list(product([lbases.ShenNeumannBasis, lbases.ShenDirichletBasis], lquads)))

@pytest.mark.parametrize('ST,quad', dirichlet_with_quads)
def test_ADDmat(ST, quad):
    M = 2*N
    ST = ST(M, quad=quad, plan=True)
    u = (1-x**2)*sin(np.pi*x)
    f = u.diff(x, 2)
    ul = lambdify(x, u, 'numpy')
    fl = lambdify(x, f, 'numpy')
    points, weights = ST.points_and_weights(M)
    uj = ul(points)
    fj = fl(points)
    s = ST.slice()

    if isinstance(ST, shenfun.chebyshev.bases.ChebyshevBase):
        A = inner_product((ST, 0), (ST, 2))
    else:
        A = inner_product((ST, 1), (ST, 1))

    f_hat = np.zeros(M)
    f_hat = ST.scalar_product(fj, f_hat)
    if isinstance(ST, shenfun.legendre.bases.LegendreBase):
        f_hat *= -1

    # Test both solve interfaces
    c_hat = f_hat.copy()
    c_hat = A.solve(c_hat)

    u_hat = np.zeros_like(f_hat)
    u_hat = A.solve(f_hat, u_hat)

    assert np.allclose(c_hat[s], u_hat[s])

    u0 = np.zeros(M)
    u0 = ST.backward(u_hat, u0)
    assert np.allclose(u0, uj)

    u1 = np.zeros(M)
    u1 = ST.forward(uj, u1)
    c = np.zeros_like(u1)
    c = A.matvec(u1, c)
    s = ST.slice()
    assert np.allclose(c[s], f_hat[s])

#test_ADDmat(lbases.ShenDirichletBasis, "GL")

biharmonic_with_quads = (list(product([cbases.ShenBiharmonicBasis], cquads)) +
                        list(product([lbases.ShenBiharmonicBasis], lquads)))

@pytest.mark.parametrize('SB,quad', biharmonic_with_quads)
def test_SBBmat(SB, quad):
    M = 72
    SB = SB(M, quad=quad, plan=True)
    u = sin(4*pi*x)**2
    f = u.diff(x, 4)
    ul = lambdify(x, u, 'numpy')
    fl = lambdify(x, f, 'numpy')
    points, weights = SB.points_and_weights(M)
    uj = ul(points)
    fj = fl(points)

    if isinstance(SB, shenfun.chebyshev.bases.ChebyshevBase):
        A = inner_product((SB, 0), (SB, 4))
    else:
        A = inner_product((SB, 2), (SB, 2))
    f_hat = np.zeros(M)
    f_hat = SB.scalar_product(fj, f_hat)
    u_hat = np.zeros(M)
    u_hat = A.solve(f_hat, u_hat)

    u0 = np.zeros(M)
    u0 = SB.backward(u_hat, u0)

    assert np.allclose(u0, uj)

    u1 = np.zeros(M)
    u1 = SB.forward(uj, u1)

    c = np.zeros_like(u1)
    c = A.matvec(u1, c)

    assert np.all(abs(c-f_hat)/c.max() < 1e-10)

    # Multidimensional
    c2 = (c.repeat(16).reshape((M, 4, 4))+1j*c.repeat(16).reshape((M, 4, 4)))
    u1 = (u1.repeat(16).reshape((M, 4, 4))+1j*u1.repeat(16).reshape((M, 4, 4)))

    c = np.zeros_like(u1)
    c = A.matvec(u1, c)

    assert np.allclose(c, c2)

#test_SBBmat(cbases.ShenBiharmonicBasis, 'GC')

@pytest.mark.parametrize('SB,quad', biharmonic_with_quads)
def test_ABBmat(SB, quad):
    M = 4*N
    SB = SB(M, quad=quad, plan=True)
    u = sin(6*pi*x)**2
    f = u.diff(x, 2)
    fl = lambdify(x, f, "numpy")
    ul = lambdify(x, u, "numpy")

    points, weights = SB.points_and_weights(M)
    uj = ul(points)
    fj = fl(points)

    f_hat = np.zeros(M)
    f_hat = SB.scalar_product(fj, f_hat)
    if isinstance(SB, shenfun.chebyshev.bases.ChebyshevBase):
        A = inner_product((SB, 0), (SB, 2))
    else:
        A = inner_product((SB, 1), (SB, 1))
        f_hat *= -1.0

    u_hat = np.zeros(M)
    u_hat[:-4] = la.spsolve(A.diags(), f_hat[:-4])
    u_hat = A.solve(f_hat, u_hat)

    u0 = np.zeros(M)
    u0 = SB.backward(u_hat, u0)
    assert np.allclose(u0, uj)

    u1 = np.zeros(M)
    u1 = SB.forward(uj, u1)
    c = np.zeros_like(u1)
    c = A.matvec(u1, c)

    assert np.allclose(c, f_hat, 1e-6, 1e-6)

    # Multidimensional
    f_hat = (f_hat.repeat(16).reshape((M, 4, 4))+1j*f_hat.repeat(16).reshape((M, 4, 4)))
    u1 = (u1.repeat(16).reshape((M, 4, 4))+1j*u1.repeat(16).reshape((M, 4, 4)))

    c = np.zeros_like(u1)
    c = A.matvec(u1, c)

    assert np.allclose(c, f_hat, 1e-6, 1e-6)

    B = inner_product((SB, 0), (SB, 0))

    u0 = np.random.randn(M)
    u0_hat = np.zeros(M)
    u0_hat = SB.forward(u0, u0_hat)
    u0 = SB.backward(u0_hat, u0)
    b = np.zeros(M)
    k = 2.
    c0 = np.zeros_like(u0_hat)
    c1 = np.zeros_like(u0_hat)
    b = A.matvec(u0_hat, c0) - k**2*B.matvec(u0_hat, c1)
    AA = A.diags().toarray() - k**2*B.diags().toarray()
    z0_hat = np.zeros(M)
    z0_hat[:-4] = solve(AA, b[:-4])
    z0 = np.zeros(M)
    z0 = SB.backward(z0_hat, z0)
    assert np.allclose(z0, u0)

#test_ABBmat(lbases.ShenBiharmonicBasis, 'LG')
