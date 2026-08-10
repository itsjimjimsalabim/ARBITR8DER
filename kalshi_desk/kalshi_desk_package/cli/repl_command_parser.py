def parse_buy_args(args: str):
    """Parse buy command arguments."""
    parts = args.split()
    if len(parts) < 3:
        return None, "Usage: buy ASSET SIDE N [LIMIT_CENTS]\n  ASSET: BTC or ETH\n  SIDE: yes or no\n  N: number of contracts (min 2)\n  LIMIT_CENTS: optional limit price in cents"

    asset = parts[0].upper()
    side = parts[1].lower()
    try:
        contracts = int(parts[2])
    except ValueError:
        return None, "Error: contracts must be a number"

    limit_cents = None
    if len(parts) >= 4 and parts[3].upper() == "LIMIT":
        if len(parts) >= 5:
            try:
                limit_cents = int(parts[4])
            except ValueError:
                return None, "Error: limit cents must be a number"
        else:
            return None, "Usage: buy ASSET SIDE N LIMIT CENTS"
    elif len(parts) >= 4:
        try:
            limit_cents = int(parts[3])
        except ValueError:
            return None, "Error: limit cents must be a number"

    if asset not in ("BTC", "ETH"):
        return None, "Error: asset must be BTC or ETH"
    if side not in ("yes", "no"):
        return None, "Error: side must be yes or no"

    return {"asset": asset, "side": side, "contracts": contracts, "limit_cents": limit_cents}, None

def parse_sell_args(args: str):
    """Parse sell command arguments."""
    parts = args.split()
    if len(parts) < 2:
        return None, "Usage: sell ASSET TICKER\n  Close the position for a specific ticker."

    return {"asset": parts[0].upper(), "ticker": parts[1]}, None
