"""Builtins implemented in Python.

This module is frozen into the interpreter and imported during startup,
before the import system exists.  The names listed in ``__all__`` are
copied into the ``builtins`` module.
"""

__all__ = ['aiter', 'anext']

_NOT_GIVEN = sentinel("_NOT_GIVEN")

# _type_lookup(cls, name, default) is implemented in Python/bltinmodule.c and
# added to this module when the interpreter starts.  It calls
# _PyType_LookupRef(): it looks a name up in the MRO of a type (not on its
# metaclass) and returns what it finds without invoking any descriptor.


def _call_special(method, obj, *args):
    # Call a special method found by _type_lookup() on type(obj) the way
    # the C slots do.  Plain functions and the method descriptors of C types
    # are bound by passing the object as the first argument.  Any other
    # descriptor is bound with its __get__, and an object that is not a
    # descriptor is called as is.
    kind = type(method)
    if (kind is _FunctionType or kind is _WrapperDescriptorType
            or kind is _MethodDescriptorType):
        return method(obj, *args)
    descr_get = _type_lookup(kind, '__get__', _NOT_GIVEN)
    if descr_get is not _NOT_GIVEN:
        method = _call_special(descr_get, method, obj, type(obj))
    return method(*args)


_FunctionType = type(_call_special)
_WrapperDescriptorType = type(object.__init__)
_MethodDescriptorType = type(str.join)


def aiter(object, /, stop_value=_NOT_GIVEN, *, stop_exception=_NOT_GIVEN):
    """Return an AsyncIterator for an AsyncIterable object.

    In the second form, the callable is called and its result is awaited
    until it returns the stop value or raises the specified exception.
    """
    if stop_value is _NOT_GIVEN and stop_exception is _NOT_GIVEN:
        cls = type(object)
        aiter_method = _type_lookup(cls, '__aiter__', _NOT_GIVEN)
        kind = type(aiter_method)
        if (kind is _FunctionType or kind is _WrapperDescriptorType
                or kind is _MethodDescriptorType):
            # The common cases of _call_special(), without the extra call.
            iterator = aiter_method(object)
        elif aiter_method is _NOT_GIVEN:
            raise TypeError(
                f"'{cls.__name__}' object is not an async iterable"
            )
        else:
            iterator = _call_special(aiter_method, object)
        anext_method = _type_lookup(type(iterator), '__anext__', _NOT_GIVEN)
        if anext_method is _NOT_GIVEN:
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
    anext_method = _type_lookup(cls, '__anext__', _NOT_GIVEN)
    kind = type(anext_method)
    if (kind is _FunctionType or kind is _WrapperDescriptorType
            or kind is _MethodDescriptorType):
        # The common cases of _call_special(), without the extra call.
        awaitable = anext_method(async_iterator)
    elif anext_method is _NOT_GIVEN:
        raise TypeError(
            f"{cls.__name__!r} object is not an async iterator"
        )
    else:
        awaitable = _call_special(anext_method, async_iterator)
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
