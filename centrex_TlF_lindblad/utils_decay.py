import copy
from dataclasses import dataclass
from typing import Any, Dict, Sequence, List, Tuple, Union

import numpy as np
import numpy.typing as npt
import sympy as smp
from centrex_tlf_hamiltonian import states

__all__ = ["DecayChannel"]


@dataclass
class DecayChannel:
    ground: states.State
    excited: states.QuantumSelector
    branching: float
    description: str = ""


def add_levels_symbolic_hamiltonian(
    hamiltonian: smp.matrices.dense.MutableDenseMatrix,
    decay_channels: Sequence[DecayChannel],
    QN: Sequence[states.State],
    excited_states: Sequence[states.State],
) -> Tuple[List[int], smp.matrices.dense.MutableDenseMatrix]:
    arr = hamiltonian.copy()
    indices = get_insert_level_indices(decay_channels, QN, excited_states)
    for idx in indices:
        arr = add_level_symbolic_hamiltonian(arr, idx)
    return indices, arr

def get_insert_level_indices(decay_channels: Sequence[DecayChannel], QN: Sequence[states.State], excited_states: Sequence[states.State]):
    indices = [i + len(QN) - len(excited_states) for i in range(len(decay_channels))]
    return indices


def add_level_symbolic_hamiltonian(
    hamiltonian: smp.matrices.dense.MutableDenseMatrix, idx: int
) -> smp.matrices.dense.MutableDenseMatrix:
    arr = hamiltonian.copy()
    arr = arr.row_insert(idx, smp.zeros(1, arr.shape[1]))
    arr = arr.col_insert(idx, smp.zeros(arr.shape[0], 1))
    return arr


def add_states_QN(
    decay_channels: Sequence[DecayChannel], QN: List[states.State], indices: List[int]
) -> List[states.State]:
    states = copy.copy(QN)
    for idx, decay_channel in zip(indices, decay_channels):
        states.insert(idx, decay_channel.ground)
    return states


def add_levels_C_array(
    C_array: npt.NDArray[np.float_], indices: List[int]
) -> npt.NDArray[np.float_]:
    arr = C_array.copy()
    # inserting rows and columns of zeros to account for the new decay levels
    for idx in indices:
        arr = np.insert(arr, idx, np.zeros(arr.shape[2]), 1)
        arr = np.insert(arr, idx, np.zeros(arr.shape[1]), 2)
    return arr


def add_decays_C_arrays(
    decay_channels: Sequence[DecayChannel],
    indices: List[int],
    QN: Sequence[states.State],
    C_array: npt.NDArray[np.float_],
    Γ: float,
) -> npt.NDArray[np.float_]:
    # converting the C arrays to branching ratio arrays and adding the new
    # levels
    BR = add_levels_C_array(C_array, indices)
    BR = BR ** 2 / Γ

    # getting the excited state indices
    indices_excited = [
        decay_channel.excited.get_indices(QN) for decay_channel in decay_channels
    ]
    # getting the total added branching ratios for each excited state
    BR_added: Dict[int, float] = {}
    for ides, decay_channel in zip(indices_excited, decay_channels):
        for ide in ides:
            if BR_added.get(ide) is None:
                BR_added[ide] = decay_channel.branching
            else:
                BR_added[ide] += decay_channel.branching
    # renormalizing the old branching ratios to ensure the sum is 1 when adding
    # the new branching ratios
    for ide, BR_add in BR_added.items():
        BR[:, :, ide] *= 1 - BR_add

    # adding the new branching ratios
    for idg, ides, decay_channel in zip(indices, indices_excited, decay_channels):
        for ide in ides:
            BR_new = np.zeros([1, *BR[0, :, :].shape], dtype=complex)
            BR_new[:, idg, ide] = decay_channel.branching
            BR = np.append(BR, BR_new, axis=0)
    # converting the branching ratios to C arrays
    return np.sqrt(BR * Γ)
