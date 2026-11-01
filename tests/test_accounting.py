import random
import pytest
from settlebook.accounting import money, split, net, settle


@pytest.mark.parametrize(
    "value,expected", [("0.01", 1), ("33.34", 3334), ("100", 10000), ("1000000000.00", 100000000000)]
)
def test_money(value, expected):
    assert money(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "1e3", "1.001", "1,000", 1.2, None, "1000000000.01", ""])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        money(value)


def test_rounding():
    assert split(10000, ["c", "a", "b"]) == {"a": 3334, "b": 3333, "c": 3333}
    assert split(1, ["a", "b"]) == {"a": 1, "b": 0}


def test_custom():
    assert split(100, ["a", "b"], "custom", {"a": 0, "b": 100}) == {"a": 0, "b": 100}
    for bad in ({"a": 50, "b": 49}, {"a": 101, "b": -1}, {"a": 50.0, "b": 50}, {"a": 100}, {"a": 50, "b": 50, "c": 0}):
        with pytest.raises(ValueError):
            split(100, ["a", "b"], "custom", bad)


def test_group_sample_and_conservation():
    people = ["sahil", "bhushan", "priya", "alex"]
    expenses = [(p, n, split(n, people)) for p, n in zip(people, [20000, 8000, 6000, 4000])]
    balances = net(expenses, people)
    assert balances == {"sahil": 10500, "bhushan": -1500, "priya": -3500, "alex": -5500}
    for debtor, creditor, n in settle(balances):
        balances[debtor] += n
        balances[creditor] -= n
    assert all(v == 0 for v in balances.values())


@pytest.mark.parametrize("seed", range(100))
def test_random_settlement_preserves_cents(seed):
    rng = random.Random(seed)
    people = [str(i) for i in range(rng.randint(2, 40))]
    expenses = []
    for _ in range(50):
        total = rng.randint(1, 1000000)
        subset = rng.sample(people, rng.randint(1, len(people)))
        shares = split(total, subset)
        assert sum(shares.values()) == total
        expenses.append((rng.choice(people), total, shares))
    balances = net(expenses, people)
    transfers = settle(balances)
    assert transfers == settle(dict(reversed(list(balances.items()))))
    assert len(transfers) <= len(people) - 1
    for d, c, n in transfers:
        assert n > 0
        balances[d] += n
        balances[c] -= n
    assert set(balances.values()) == {0}


def test_invalid_membership_and_net():
    with pytest.raises(ValueError):
        net([("outsider", 100, {"a": 100})], ["a"])
    with pytest.raises(ValueError):
        settle({"a": 10, "b": -9})
    with pytest.raises(ValueError):
        split(100, ["a", "a"])
