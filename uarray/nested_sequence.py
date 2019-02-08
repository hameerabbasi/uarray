"""
Support compiling to, and reading from, nested python tuples as arrays.
"""
import dataclasses
import typing
import itertools
import functools
from .core import *
from .dispatch import *

T_box = typing.TypeVar("T_box", bound=Box)
U_box = typing.TypeVar("U_box", bound=Box)
T = typing.TypeVar("T")
U = typing.TypeVar("U")
V = typing.TypeVar("V")
ctx = MapChainCallable()
default_context.append(ctx)

__all__ = ["create_python_array", "to_python_array", "create_python_bin_abs"]


@dataclasses.dataclass(frozen=True)
class NestedTuples:
    value: typing.Any


def create_python_array(shape: typing.Tuple[int, ...], data: typing.Any) -> Array:
    return Array.create(
        Array.create_shape(*map(Nat, shape)), Abstraction(NestedTuples(data), Box(None))
    )


def index_python_array(array: Array[T_box], *idx: Nat) -> T_box:
    ...


@register(ctx, Abstraction.__call__)
def __call___nested_lists(self: Abstraction[T_box, U_box], arg: T_box) -> U_box:
    if not (isinstance(self.value, NestedTuples)) or not isinstance(arg.value, VecData):
        return NotImplemented
    idx = arg.value.list.value
    if not isinstance(idx, tuple):
        return NotImplemented

    data = self.value.value
    for i in idx:
        if not isinstance(i.value, int):
            return NotImplemented
        data = data[i.value]
    return self.rettype._replace(data)


def to_python_array(a: Array[T_box]) -> Array[T_box]:
    return Array(Operation(to_python_array, (a,)), a.dtype)


@register(ctx, to_python_array)
def _to_python_array(a: Array[T_box]) -> Array[T_box]:
    return to_python_array_expanded_first(a.shape, a.idx_abs)


def to_python_array_expanded_first(
    shape: Vec[Nat], idx_abs: Abstraction[Vec[Nat], T_box]
) -> Array[T_box]:
    return Array(
        Operation(to_python_array_expanded_first, (shape, idx_abs)), idx_abs.rettype
    )


@register(ctx, to_python_array_expanded_first)
def _to_python_array_expanded_first(
    shape: Vec[Nat], idx_abs: Abstraction[Vec[Nat], T_box]
) -> Array[T_box]:
    # If contentst is already nested tuples, we can stop now.
    if isinstance(idx_abs.value, NestedTuples):
        return Array.create(shape, idx_abs)
    if not isinstance(shape.value, VecData):
        return NotImplemented
    shape_list = shape.value.list
    if not isinstance(shape_list.value, tuple):
        return NotImplemented
    shape_items: typing.Tuple[Nat, ...] = shape_list.value
    if not all(isinstance(i, int) for i in shape_items):
        return NotImplemented
    shape_items_ints: typing.Tuple[int, ...] = tuple(i.value for i in shape_items)

    # iterate through all combinations of shape list
    # create list that has all of these
    all_possible_idxs = list(itertools.product(*(range(i) for i in shape_items_ints)))

    contents = List.create(
        idx_abs.rettype,
        *(idx_abs(Array.create_shape(*map(Nat, idx))) for idx in all_possible_idxs)
    )

    return to_python_array_expanded(shape, contents)


def to_python_array_expanded(shape: Vec[Nat], contents: List[T_box]) -> Array[T_box]:
    return Array(Operation(to_python_array_expanded, (shape, contents)), contents.dtype)


@register(ctx, to_python_array_expanded)
def _to_python_array_expanded(shape: Vec[Nat], contents: List[T_box]) -> Array[T_box]:
    if not shape._concrete:
        return NotImplemented
    shape_length, shape_list = shape.value.args
    if not shape_length._concrete or not shape_list._concrete:
        return NotImplemented
    shape_items: typing.Tuple[Nat, ...] = shape_list.value.args
    if not all(i._concrete for i in shape_items):
        return NotImplemented

    if not contents._concrete:
        return NotImplemented
    shape_items_ints: typing.Tuple[int, ...] = tuple(i.value for i in shape_items)

    all_possible_idxs = list(itertools.product(*(range(i) for i in shape_items_ints)))

    def inner(s, i):
        if s:
            return tuple(inner(s[1:], i + (idx,)) for idx in range(s[0]))

        flattened_idx = all_possible_idxs.index(i)
        content = contents.value.args[flattened_idx]
        if not isinstance(content, PythonScalar):
            return NotImplemented
        return content.value

    return create_python_array(shape_items_ints, inner(shape_items_ints, ()))


def create_python_bin_abs(
    fn: typing.Callable[[T, U], V], l_type: typing.Type[T], r_type: typing.Type[U]
) -> Abstraction[Box[T], Abstraction[Box[U], Box[V]]]:

    return Abstraction.create_nary_native(
        lambda a, b: Box(fn(a.value, b.value)),
        Box(None),
        lambda a: isinstance(a.value, l_type),
        lambda b: isinstance(b.value, r_type),
    )
