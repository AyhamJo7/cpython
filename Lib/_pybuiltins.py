"""Builtins implemented in Python.

This module is frozen into the interpreter and imported during startup,
before the import system exists.  The names listed in ``__all__`` are
copied into the ``builtins`` module.
"""

__all__ = ['aiter', 'anext']

_NOT_GIVEN = sentinel("_NOT_GIVEN")
_type_mro = type.__dict__['__mro__'].__get__
_type_dict = type.__dict__['__dict__'].__get__


def _find_special(cls, name):
    # Find a special method the way the C slots do: only in the MRO of
    # the type (not on the instance or the metaclass), without invoking
    # any descriptor.
    for base in _type_mro(cls):
        namespace = _type_dict(base)
        if name in namespace:
            return namespace[name]
    return _NOT_GIVEN


def _bind_special(method, obj):
    # Bind a special method with the descriptor protocol, so that class
    # methods, other descriptors and callables that are not descriptors
    # are called the same way as by "async for".
    try:
        descr_get = type(method).__get__
    except AttributeError:
        return method
    return descr_get(method, obj, type(obj))


# Plain functions and the method descriptors of C types are called with the
# object as the first argument, and getting them from the type returns them
# unchanged, so aiter() and anext() can use the fast attribute lookup for
# them.  A staticmethod wrapping one of them cannot be told apart this way
# and is still called with the object.
_FunctionType = type(_find_special)
_WrapperDescriptorType = type(object.__init__)
_MethodDescriptorType = type(str.join)


def aiter(object, /, stop_value=_NOT_GIVEN, *, stop_exception=_NOT_GIVEN):
    """Return an AsyncIterator for an AsyncIterable object.

    In the second form, the callable is called and its result is awaited
    until it returns the stop value or raises the specified exception.
    """
    if stop_value is _NOT_GIVEN and stop_exception is _NOT_GIVEN:
        cls = type(object)
        try:
            # The fast lookup; it is only used as is for the kinds of
            # attributes that the C slot am_aiter calls with the object.
            aiter_method = cls.__aiter__
        except AttributeError:
            aiter_method = _NOT_GIVEN
        kind = type(aiter_method)
        if (kind is _FunctionType or kind is _WrapperDescriptorType
                or kind is _MethodDescriptorType):
            iterator = aiter_method(object)
        else:
            aiter_method = _find_special(cls, '__aiter__')
            if aiter_method is _NOT_GIVEN:
                raise TypeError(
                    f"'{cls.__name__}' object is not an async iterable"
                )
            iterator = _bind_special(aiter_method, object)()
        if _find_special(type(iterator), '__anext__') is _NOT_GIVEN:
            raise TypeError(
                f"{cls.__name__}.__aiter__() must return an async iterator, "
                f"not {type(iterator).__name__}"
            )
        return iterator

    if not callable(object):
        raise TypeError("aiter(): the first argument must be callable")
    if stop_exception is _NOT_GIVEN:
        stop_exception = StopAsyncIteration
    else:
        # Like _PyEval_CheckExceptTypeValid(): an exception class or a tuple
        # of exception classes.
        if isinstance(stop_exception, tuple):
            items = stop_exception
        else:
            items = (stop_exception,)
        for item in items:
            if not (isinstance(item, type) and issubclass(item, BaseException)):
                raise TypeError(
                    "catching classes that do not inherit from BaseException "
                    "is not allowed"
                )
    return async_callable_iterator(object, stop_value, stop_exception)


class async_callable_iterator:
    """The asynchronous counterpart of callable_iterator.

    The callable is called and its result is awaited for every
    __anext__().
    """

    __slots__ = ('_callable', '_stop_value', '_stop_exception')
    __module__ = 'builtins'

    def __init__(self, callable, stop_value, stop_exception):
        # _callable is set to None when the iterator is exhausted.
        self._callable = callable
        self._stop_value = stop_value
        self._stop_exception = stop_exception

    def __aiter__(self):
        return self

    async def __anext__(self):
        callable = self._callable
        if callable is None:
            raise StopAsyncIteration
        try:
            value = await callable()
        except self._stop_exception:
            self._exhaust()
            raise StopAsyncIteration from None
        except (StopIteration, StopAsyncIteration) as exc:
            raise RuntimeError(
                f"callable raised {type(exc).__name__}") from exc
        stop_value = self._stop_value
        if stop_value is not _NOT_GIVEN and stop_value == value:
            self._exhaust()
            raise StopAsyncIteration
        return value

    def _exhaust(self):
        self._callable = None
        self._stop_value = _NOT_GIVEN


def anext(async_iterator, default=_NOT_GIVEN, /):
    """Return the next item from the async iterator.

    If default is given and the async iterator is exhausted,
    it is returned instead of raising StopAsyncIteration.
    """
    cls = type(async_iterator)
    try:
        # The fast lookup; it is only used as is for the kinds of
        # attributes that the C slot am_anext calls with the object.
        anext_method = cls.__anext__
    except AttributeError:
        anext_method = _NOT_GIVEN
    kind = type(anext_method)
    if (kind is _FunctionType or kind is _WrapperDescriptorType
            or kind is _MethodDescriptorType):
        awaitable = anext_method(async_iterator)
    else:
        anext_method = _find_special(cls, '__anext__')
        if anext_method is _NOT_GIVEN:
            raise TypeError(
                f"{cls.__name__!r} object is not an async iterator"
            )
        awaitable = _bind_special(anext_method, async_iterator)()
    if default is _NOT_GIVEN:
        return awaitable
    return _anext_with_default(awaitable, default)


async def _anext_with_default(awaitable, default):
    try:
        return await awaitable
    except StopAsyncIteration:
        return default


for _name in __all__:
    globals()[_name].__module__ = 'builtins'
del _name
