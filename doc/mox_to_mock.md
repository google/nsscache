# Translating pymox to unittest.mock

## Creating a mock object

self.mox.CreateMock({}) -> mock.create_autospec({})

## Creating a mock anything

self.mox.CreateMockAnything() ->> mock.Mock()

## Matching arguments and mockign return value

{}.fn(args...).AndReturn(ret) ->

{}.fn.return_value = ret

... after act phase

{}.fn.assert_called_with(args)

## Replacing attributes with mocks

self.mox.StubOutWithMock(a, b) ->

a.b = mock.Mock()

## Replacing class with mocks

self.moxk.StubOutClassWithMocks(a, b) ->

@mock.patch.object(a, b)


## Ignoring arguments

mox.IgnoreArg() -> mock.ANY

## Multiple return values

multiple return values ->  side_effect=[...]

## Raising exceptions

{}.AndRaise(r) -> {}.side_effect=r
