"""Pure, deterministic integer arithmetic; no I/O."""

import re

MAX_CENTS = 100_000_000_000


def money(value, allow_zero=False):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,10}(\.\d{1,2})?", value):
        raise ValueError("Enter a positive decimal amount with at most two decimal places.")
    whole, _, fraction = value.partition(".")
    n = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if n > MAX_CENTS or n < (0 if allow_zero else 1):
        raise ValueError("Amount is outside the permitted range.")
    return n


def split(total, people, method="equal", custom=None):
    people = sorted(people)
    if not people or len(people) != len(set(people)):
        raise ValueError("Select distinct participants.")
    if type(total) is not int or not 0 < total <= MAX_CENTS:
        raise ValueError("Invalid total.")
    if method == "equal":
        q, r = divmod(total, len(people))
        return {p: q + (i < r) for i, p in enumerate(people)}
    if method != "custom" or set(custom or {}) != set(people):
        raise ValueError("Supply every custom share.")
    if any(type(n) is not int or n < 0 for n in custom.values()) or sum(custom.values()) != total:
        raise ValueError("Shares must be nonnegative cents and sum exactly to the bill total.")
    return {p: custom[p] for p in people}


def net(expenses, people):
    result = {p: 0 for p in people}
    for payer, total, shares in expenses:
        if payer not in result or set(shares) - result.keys():
            raise ValueError("Invalid membership.")
        split(total, list(shares), "custom", shares)
        result[payer] += total
        for p, n in shares.items():
            result[p] -= n
    if sum(result.values()):
        raise ValueError("Group is not balanced.")
    return result


def settle(balances):
    if any(type(v) is not int for v in balances.values()) or sum(balances.values()):
        raise ValueError("Invalid balances.")
    debtors = [[p, -v] for p, v in sorted(balances.items()) if v < 0]
    creditors = [[p, v] for p, v in sorted(balances.items()) if v > 0]
    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        result.append((debtors[i][0], creditors[j][0], amount))
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return result
