import copy
from typing import Any, List, Literal, Optional, Sequence, Tuple, Union, overload

import numpy as np
import numpy.typing as npt
import sympy as smp
from centrex_tlf_hamiltonian import states
import centrex_tlf_couplings as couplings_TlF
from .utils_compact import compact_symbolic_hamiltonian_indices

__all__ = [
    "symbolic_hamiltonian_to_rotating_frame",
    "generate_symbolic_hamiltonian",
    "generate_total_symbolic_hamiltonian",
]


def symbolic_hamiltonian_to_rotating_frame(
    hamiltonian: smp.matrices.dense.MutableDenseMatrix,
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: Sequence[couplings_TlF.CouplingFields],
    δs: Sequence[smp.Symbol],
) -> smp.matrices.dense.MutableDenseMatrix:
    """Transform a symbolic hamiltonian to the rotating frame. Exponential terms
    with the transition frequencies are required to be present in the
    hamiltonian matrix, as well as symbolic energies on the diagonal.

    Args:
        hamiltonian (sympy.Matrix): symbolic hamiltonian
        QN (list/array): list/array of states in the system
        H_int (np.ndarray): numerical hamiltonian, energies only
        couplings (list): list of couplings in system

    Returns:
        sympy.Matrix: symbolic hamiltonian in the rotating frame
    """
    n_states = H_int.shape[0]
    energies = np.diag(hamiltonian)

    # generate t symbol for non-rotating frame
    t = smp.Symbol("t", real=True)

    coupled_states = []
    for i, j in zip(*np.nonzero(hamiltonian)):
        if i < j:
            syms = hamiltonian[i, j].free_symbols
            syms = [s for s in syms if str(s)[0] == "ω"]
            assert len(syms) == 1, f"Too many/few couplings, syms = {syms}"
            coupled_states.append((i, j, syms[0]))

    # solve equations to generate unitary transformation to rotating frame
    A = smp.symbols(f"a:{n_states}")
    Eqns = []
    # generate equations
    for i, j, ω in coupled_states:
        Eqns.append(ω - (A[i] - A[j]))
    # solve system of equations
    sol = smp.solve(Eqns, A)
    # set free parameters to zero in the solution
    free_params = [value for value in A if value not in list(sol.keys())]
    for free_param in free_params:
        for key, val in sol.items():
            sol[key] = val.subs(free_param, 0)

    # generate unitary transformation matrix
    T = smp.eye(*H_int.shape)
    for var in sol.keys():
        ida = int(str(var)[1:])
        T[ida, ida] = smp.exp(1j * sol[var] * t)

    # use unitary matrix to transform to rotating frame
    transformed = T.adjoint() @ hamiltonian @ T - 1j * T.adjoint() @ smp.diff(T, t)
    transformed = smp.simplify(transformed)

    transformed = smp.Matrix(transformed)

    for idc, (δ, coupling) in enumerate(zip(δs, couplings)):
        # generate transition frequency symbol
        ω = smp.Symbol(f"ω{idc}", real=True)
        # get indices of ground and excited states
        idg = QN.index(coupling.ground_main)
        ide = QN.index(coupling.excited_main)
        # transform to δ instead of ω and E
        transformed = transformed.subs(ω, energies[ide] - energies[idg] + δ)

    # substitute level energies for symbolic values
    transformed = transformed.subs(
        [(E, val) for E, val in zip(energies, np.diag(H_int))]
    )

    # set energie difference between excited and ground states to zero
    # should be done automatically when solving for the unitary matrix, not sure
    # why this is not happening currently
    for coupling in couplings:
        idg = QN.index(coupling.ground_main)
        ide = QN.index(coupling.excited_main)
        indices_ground = [QN.index(s) for s in coupling.ground_states]
        indices_excited = [QN.index(s) for s in coupling.excited_states]
        g = transformed[idg, idg].subs(
            [(s, 0) for s in transformed[idg, idg].free_symbols]
        )
        e = transformed[ide, ide].subs(
            [(s, 0) for s in transformed[ide, ide].free_symbols]
        )
        for idg in indices_ground:
            transformed[idg, idg] -= g
        for ide in indices_excited:
            transformed[ide, ide] -= e

    return transformed


def generate_symbolic_hamiltonian(
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: Sequence[couplings_TlF.CouplingFields],
    Ωs: Sequence[smp.Symbol],
    δs: Sequence[smp.Symbol],
    pols: List[Optional[Sequence[smp.Symbol]]],
) -> smp.matrices.dense.MutableDenseMatrix:
    n_states = H_int.shape[0]
    # initialize empty hamiltonian
    hamiltonian = smp.zeros(*H_int.shape)
    energies = smp.symbols(f"E:{n_states}")
    hamiltonian += smp.eye(n_states) * np.asarray(energies)

    # generate t symbol for non-rotating frame
    t = smp.Symbol("t", real=True)

    # iterate over couplings
    for idc, (Ω, coupling) in enumerate(zip(Ωs, couplings)):
        # generate transition frequency symbol
        ω = smp.Symbol(f"ω{idc}", real=True)
        # main coupling matrix element
        main_coupling = coupling.main_coupling
        # iterate over fields (polarizations) in the coupling
        for idf, field in enumerate(coupling.fields):
            if pols:
                P = pols[idc]
                if P:
                    _P = P[idf]
                    val = (_P * Ω / main_coupling) / 2
                    for i, j in zip(*np.nonzero(field.field)):
                        if i < j:
                            hamiltonian[i, j] += (
                                val * field.field[i, j] * smp.exp(1j * ω * t)
                            )
                            hamiltonian[j, i] += (
                                val * field.field[j, i] * smp.exp(-1j * ω * t)
                            )
                else:
                    val = (Ω / main_coupling) / 2
                    for i, j in zip(*np.nonzero(field.field)):
                        if i < j:
                            hamiltonian[i, j] += (
                                val * field.field[i, j] * smp.exp(1j * ω * t)
                            )
                            hamiltonian[j, i] += (
                                val * field.field[j, i] * smp.exp(-1j * ω * t)
                            )
            else:
                val = (Ω / main_coupling) / 2
                for i, j in zip(*np.nonzero(field.field)):
                    if i < j:
                        hamiltonian[i, j] += (
                            val * field.field[i, j] * smp.exp(1j * ω * t)
                        )
                        hamiltonian[j, i] += (
                            val * field.field[j, i] * smp.exp(-1j * ω * t)
                        )

    hamiltonian = smp.simplify(hamiltonian)

    transformed = symbolic_hamiltonian_to_rotating_frame(
        hamiltonian, QN, H_int, couplings, δs
    )
    transformed = smp.Matrix(transformed)

    Ωsᶜ = [smp.Symbol(str(Ω) + "ᶜ", complex=True) for Ω in Ωs]
    for idx in range(n_states):
        for idy in range(0, idx):
            for Ω, Ωᶜ in zip(Ωs, Ωsᶜ):
                transformed[idx, idy] = transformed[idx, idy].subs(Ω, Ωᶜ)

    return transformed


@overload
def generate_total_symbolic_hamiltonian(
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: List[couplings_TlF.CouplingFields],
    transitions: Sequence[Any],
    qn_compact: Literal[None],
) -> smp.matrices.dense.MutableDenseMatrix:
    ...


@overload
def generate_total_symbolic_hamiltonian(
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: List[couplings_TlF.CouplingFields],
    transitions: Sequence[Any],
) -> smp.matrices.dense.MutableDenseMatrix:
    ...


@overload
def generate_total_symbolic_hamiltonian(
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: Sequence[couplings_TlF.CouplingFields],
    transitions: Sequence[Any],
    qn_compact: Union[Sequence[states.QuantumSelector], states.QuantumSelector],
) -> Tuple[smp.matrices.dense.MutableDenseMatrix, List[states.State]]:
    ...


def generate_total_symbolic_hamiltonian(
    QN: List[states.State],
    H_int: npt.NDArray[np.complex_],
    couplings: Sequence[Any],
    transitions: Sequence[Any],
    qn_compact: Optional[
        Union[Sequence[states.QuantumSelector], states.QuantumSelector]
    ] = None,
) -> Union[
    Tuple[smp.matrices.dense.MutableDenseMatrix, List[states.State]],
    smp.matrices.dense.MutableDenseMatrix,
]:
    """Generate the total symbolic hamiltonian for the given system

    Args:
        QN (Sequence[states.State]): states
        H_int (np.ndarray): internal hamiltonian
        couplings (Sequence[states.State]): list of dictionaries with all couplings of
                                            the system
        transitions (Sequence[states.State]): list of dictionaries with all transitions
                                                of the system
        qn_compact (Sequence[states.State], optional): list of QuantumSelectors or lists
                                                        of QuantumSelectors with each
                                                        QuantumSelector containing the
                                                        quantum numbers to compact into
                                                        a single state.
                                                        Defaults to None.

    Returns:
        sympy matrix: symbolic hamiltonian
        if qn_compact is provided, also returns the states corresponding to the
        compacted hamiltonian, i.e. ham, QN_compact
    """
    Ωs = [t.Ω for t in transitions]
    Δs = [t.δ for t in transitions]
    pols: List[Optional[Sequence[smp.Symbol]]] = []
    for transition in transitions:
        if not transition.polarization_symbols:
            pols.append(None)
        else:
            pols.append(transition.polarization_symbols)

    H_symbolic = generate_symbolic_hamiltonian(QN, H_int, couplings, Ωs, Δs, pols)
    if qn_compact is not None:
        if isinstance(qn_compact, states.QuantumSelector):
            qn_compact = [qn_compact]
        QN_compact = copy.deepcopy(QN)
        for qnc in qn_compact:
            indices_compact = states.get_indices_quantumnumbers(qnc, QN_compact)
            QN_compact = states.compact_QN_coupled_indices(
                QN_compact, indices_compact
            )  # type: ignore
            H_symbolic = compact_symbolic_hamiltonian_indices(
                H_symbolic, indices_compact
            )
        return H_symbolic, QN_compact

    return H_symbolic
