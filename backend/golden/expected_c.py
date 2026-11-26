"""獨立 C 層財務標準答案（A 來源＋SPEC；禁用受測 FIFO／Projector）。

本模組禁止匯入受測配對器與報表投影／財務組裝服務。演算法依
``docs/spec/SPEC.md`` §6（CASH Two-Pass）與 §7（TRUNC 價金／費用第一片段）
獨立實作，供黃金驗收 expected_c 使用。
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any

from backend.util.date_text import parse_flexible_date
from backend.util.decimal_text import normalize_decimal_text
from backend.util.sha256_lock import sha256_lock_mismatches

AMOUNT_TOLERANCE = Decimal(1)


@dataclass(frozen=True)
class ExpectedTrade:
    """C 層獨立核算用成交（由 A 列推導，非 DB／受測輸出）。"""

    trade_id: str
    symbol: str
    trade_date: date
    side: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    source_order: int
    currency: str = "TWD"
    trade_type: str = "CASH"
    account_id: str = "default"
    interest_known: bool = True
    currency_known: bool = True
    trade_type_known: bool = True


@dataclass(frozen=True)
class ExpectedOpeningLot:
    """經核准期初 lot；未核准不得傳入。"""

    lot_id: str
    symbol: str
    trade_date: date
    quantity: int
    unit_price: Decimal
    currency: str = "TWD"
    account_id: str = "default"


@dataclass
class ExpectedAllocation:
    buy_trade_id: str | None
    opening_lot_id: str | None
    sell_trade_id: str
    quantity: int
    match_type: str
    sequence_no: int
    account_id: str = "default"
    symbol: str = ""
    currency: str = "TWD"


@dataclass
class FifoExpected:
    allocations: list[ExpectedAllocation] = field(default_factory=list)
    standard_fifo_allocated_qty: int = 0
    same_day_reconciled_qty: int = 0
    unmatched_sell_qty: int = 0
    unsold_buy_qty: int = 0
    blocking_insufficient_prior_buys: bool = False
    unmatched_by_sell: dict[str, int] = field(default_factory=dict)
    unsold_lots: list[dict[str, Any]] = field(default_factory=list)


def invalid_row_count_status(source_format: str) -> str:
    """回傳該來源格式之 invalid 分計狀態語意。"""
    if source_format in {"html_table_xls", "esun_xlsx"}:
        return "UNKNOWN"
    if source_format in {"capital_csv", "capital_csv_multi_year"}:
        return "CLASSIFIED"
    return "UNKNOWN"


def make_expected_trade_id(source_id: str, physical_line: int | str) -> str:
    """來源識別＋原始列號 → 全域唯一 trade_id。"""
    sid = str(source_id).strip() or "UNKNOWN_SOURCE"
    return f"{sid}:L{physical_line}"


def trade_ids_unique(trades: Sequence[ExpectedTrade]) -> bool:
    ids = [t.trade_id for t in trades]
    return len(ids) == len(set(ids))


def trunc_toward_zero(value: Decimal) -> Decimal:
    """朝零截斷為整數 Decimal（含負數）。

    注意：``decimal.ROUND_DOWN`` 語意為朝零；``ROUND_UP`` 為離零。
    不得對負數誤用 ``ROUND_UP``（會得到更負的整數）。
    """
    return value.to_integral_value(rounding=ROUND_DOWN)


def evaluate_source_integrity(
    *,
    expected_sha256: dict[str, str],
    actual_sha256: dict[str, str],
    invalid_row_count: int | str | None,
) -> dict[str, Any]:
    """重用 Phase 1 SHA256 鎖定語意＋非法列閘門；失敗保留原因。

    - 指紋不符或 invalid>0 → ``FAIL``（不得完整成功）
    - invalid=UNKNOWN（格式未驗證）→ ``PARTIAL``（可核算但不得完整成功）
    """
    hard_reasons: list[str] = []
    soft_reasons: list[str] = []
    mismatches = sha256_lock_mismatches(expected_sha256, actual_sha256)
    if mismatches:
        hard_reasons.append(f"sha256_lock_mismatch:{','.join(mismatches)}")

    if isinstance(invalid_row_count, str):
        if invalid_row_count.upper() == "UNKNOWN":
            soft_reasons.append("invalid_row_count_UNKNOWN_unverified_format")
        else:
            try:
                invalid_n = int(invalid_row_count)
            except ValueError:
                hard_reasons.append(f"invalid_row_count_unparseable:{invalid_row_count}")
            else:
                if invalid_n > 0:
                    hard_reasons.append("invalid_trade_rows_present")
    elif invalid_row_count is None:
        soft_reasons.append("invalid_row_count_missing")
    else:
        if int(invalid_row_count) > 0:
            hard_reasons.append("invalid_trade_rows_present")

    if hard_reasons:
        status = "FAIL"
    elif soft_reasons:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "status": status,
        "reasons": hard_reasons + soft_reasons,
        "hard_reasons": hard_reasons,
        "soft_reasons": soft_reasons,
        "sha256_mismatches": mismatches,
    }


def _dec(text: object) -> Decimal:
    raw = "" if text is None else str(text)
    norm = normalize_decimal_text(raw)
    if norm == "":
        raise ValueError("empty_decimal")
    return Decimal(norm)


def _dec_or_zero_if_explicit(text: object) -> tuple[Decimal, bool]:
    """回傳 (值, known)。空白 → (0, False)；明確 0／數值 → known True。"""
    raw = "" if text is None else str(text).strip()
    if raw == "":
        return Decimal(0), False
    return _dec(raw), True


def allocate_fragment_amounts(
    *,
    unit_price: Decimal,
    gross: Decimal,
    qtys: Sequence[int],
    tolerance: Decimal = AMOUNT_TOLERANCE,
) -> dict[str, Any]:
    """依 TRUNC(qty×price) 分配片段價金；超容許明確標不守恆。"""
    if not qtys:
        return {
            "amounts": [],
            "difference": "0",
            "conservation_ok": gross == 0,
            "out_of_tolerance": False,
        }
    truncated = [trunc_toward_zero(Decimal(q) * unit_price) for q in qtys]
    calculated = sum(truncated, Decimal(0))
    difference = gross - calculated
    amounts = list(truncated)
    out_of_tolerance = False
    if difference == 0:
        pass
    elif abs(difference) <= tolerance:
        amounts[-1] = amounts[-1] + difference
    else:
        out_of_tolerance = True
    return {
        "amounts": amounts,
        "difference": _norm_dec_str(difference),
        "conservation_ok": not out_of_tolerance,
        "out_of_tolerance": out_of_tolerance,
    }


def _allocate_fragment_amounts(
    unit_price: Decimal,
    gross: Decimal,
    qtys: Sequence[int],
) -> list[Decimal]:
    return list(
        allocate_fragment_amounts(unit_price=unit_price, gross=gross, qtys=qtys)["amounts"]
    )


def aggregate_source_finance(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """由 A 有效列彙總買賣股數／價金／費稅息／淨收付（費用不拆分）。"""
    buy_n = sell_n = 0
    buy_q = sell_q = Decimal(0)
    buy_g = sell_g = Decimal(0)
    buy_c = sell_c = Decimal(0)
    tax = interest = net = Decimal(0)
    interest_unknown = False
    unknown_sides: list[str] = []

    for row in rows:
        side = str(row.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            raw = str(row.get("side_raw") or "")
            if "買" in raw:
                side = "BUY"
            elif "賣" in raw:
                side = "SELL"
            else:
                unknown_sides.append(raw or "?")
                continue
        q = _dec(row["quantity"])
        g = _dec(row["gross_amount"])
        c = _dec(row["commission"])
        t = _dec(row["tax"])
        i, i_known = _dec_or_zero_if_explicit(row.get("interest", ""))
        if not i_known:
            interest_unknown = True
        n = _dec(row["net_settlement"])
        tax += t
        interest += i
        net += n
        if side == "BUY":
            buy_n += 1
            buy_q += q
            buy_g += g
            buy_c += c
        else:
            sell_n += 1
            sell_q += q
            sell_g += g
            sell_c += c

    return {
        "valid_trade_count": buy_n + sell_n,
        "buy_trade_count": buy_n,
        "sell_trade_count": sell_n,
        "buy_quantity": _norm_int_str(buy_q),
        "sell_quantity": _norm_int_str(sell_q),
        "buy_gross_amount": _norm_dec_str(buy_g),
        "sell_gross_amount": _norm_dec_str(sell_g),
        "buy_commission": _norm_dec_str(buy_c),
        "sell_commission": _norm_dec_str(sell_c),
        "tax": _norm_dec_str(tax),
        "interest": "UNKNOWN" if interest_unknown else _norm_dec_str(interest),
        "interest_known": not interest_unknown,
        "net_settlement": _norm_dec_str(net),
        "fee_landing_policy": "source_values_unsplit",
        "unknown_side_count": len(unknown_sides),
    }


def _norm_int_str(value: Decimal) -> str:
    return str(int(value))


def _norm_dec_str(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def independent_cash_fifo(
    trades: Sequence[ExpectedTrade],
    *,
    opening_lots: Iterable[ExpectedOpeningLot] = (),
) -> FifoExpected:
    """依 SPEC §6 CASH Two-Pass；分組鍵含 account／currency，禁止跨幣別／帳戶混配。"""
    openings = list(opening_lots)
    by_pool: dict[tuple[str, str, str], list[ExpectedTrade]] = defaultdict(list)
    for t in trades:
        if not t.trade_type_known or t.trade_type != "CASH":
            continue
        if not t.currency_known:
            continue
        if t.side not in {"BUY", "SELL"}:
            continue
        by_pool[(t.account_id, t.symbol, t.currency)].append(t)

    result = FifoExpected()
    seq = 0

    for account_id, symbol, currency in sorted(by_pool):
        sym_trades = sorted(
            by_pool[(account_id, symbol, currency)],
            key=lambda t: (t.trade_date, t.source_order, t.trade_id),
        )
        fifo: deque[dict[str, Any]] = deque()
        for lot in sorted(
            [
                o
                for o in openings
                if o.symbol == symbol
                and o.account_id == account_id
                and o.currency == currency
            ],
            key=lambda o: (o.trade_date, o.lot_id),
        ):
            fifo.append(
                {
                    "buy_trade_id": None,
                    "opening_lot_id": lot.lot_id,
                    "date": lot.trade_date,
                    "avail": lot.quantity,
                    "unit_price": lot.unit_price,
                }
            )

        days = sorted({t.trade_date for t in sym_trades})
        for day in days:
            day_sells = sorted(
                [t for t in sym_trades if t.trade_date == day and t.side == "SELL"],
                key=lambda t: (t.source_order, t.trade_id),
            )
            day_buys = sorted(
                [t for t in sym_trades if t.trade_date == day and t.side == "BUY"],
                key=lambda t: (t.source_order, t.trade_id),
            )
            pending: list[tuple[ExpectedTrade, int]] = []

            for sell in day_sells:
                left = sell.quantity
                while left > 0 and fifo and fifo[0]["date"] <= sell.trade_date:
                    lot = fifo[0]
                    matched = min(int(lot["avail"]), left)
                    seq += 1
                    result.allocations.append(
                        ExpectedAllocation(
                            buy_trade_id=lot["buy_trade_id"],
                            opening_lot_id=lot["opening_lot_id"],
                            sell_trade_id=sell.trade_id,
                            quantity=matched,
                            match_type="STANDARD_FIFO",
                            sequence_no=seq,
                            account_id=account_id,
                            symbol=symbol,
                            currency=currency,
                        )
                    )
                    result.standard_fifo_allocated_qty += matched
                    lot["avail"] -= matched
                    left -= matched
                    if lot["avail"] == 0:
                        fifo.popleft()
                if left > 0:
                    pending.append((sell, left))

            for buy in day_buys:
                fifo.append(
                    {
                        "buy_trade_id": buy.trade_id,
                        "opening_lot_id": None,
                        "date": buy.trade_date,
                        "avail": buy.quantity,
                        "unit_price": buy.unit_price,
                    }
                )

            for sell, left in pending:
                remain = left
                while (
                    remain > 0
                    and fifo
                    and fifo[0]["date"] == day
                    and fifo[0]["buy_trade_id"]
                ):
                    lot = fifo[0]
                    matched = min(int(lot["avail"]), remain)
                    seq += 1
                    result.allocations.append(
                        ExpectedAllocation(
                            buy_trade_id=lot["buy_trade_id"],
                            opening_lot_id=None,
                            sell_trade_id=sell.trade_id,
                            quantity=matched,
                            match_type="SAME_DAY_RECONCILED",
                            sequence_no=seq,
                            account_id=account_id,
                            symbol=symbol,
                            currency=currency,
                        )
                    )
                    result.same_day_reconciled_qty += matched
                    lot["avail"] -= matched
                    remain -= matched
                    if lot["avail"] == 0:
                        fifo.popleft()
                if remain > 0:
                    result.unmatched_sell_qty += remain
                    result.unmatched_by_sell[sell.trade_id] = (
                        result.unmatched_by_sell.get(sell.trade_id, 0) + remain
                    )
                    result.blocking_insufficient_prior_buys = True

        for lot in fifo:
            avail = int(lot["avail"])
            if avail <= 0:
                continue
            result.unsold_buy_qty += avail
            result.unsold_lots.append(
                {
                    "buy_trade_id": lot["buy_trade_id"],
                    "opening_lot_id": lot["opening_lot_id"],
                    "account_id": account_id,
                    "symbol": symbol,
                    "currency": currency,
                    "trade_date": lot["date"].isoformat(),
                    "quantity": avail,
                    "unit_price": str(lot["unit_price"]),
                }
            )

    return result


def compute_realized_and_open(
    trades: Sequence[ExpectedTrade],
    fifo: FifoExpected,
) -> dict[str, Any]:
    """依 SPEC §7 獨立核算已實現損益、未平倉與逐筆配對行。"""
    by_id = {t.trade_id: t for t in trades}
    buy_alloc_qtys: dict[str, list[int]] = defaultdict(list)
    sell_alloc_qtys: dict[str, list[int]] = defaultdict(list)
    buy_alloc_pairs: list[tuple[str, str, int, str, ExpectedAllocation]] = []
    for alloc in sorted(fifo.allocations, key=lambda a: a.sequence_no):
        if alloc.buy_trade_id:
            buy_alloc_qtys[alloc.buy_trade_id].append(alloc.quantity)
            buy_alloc_pairs.append(
                (
                    alloc.buy_trade_id,
                    alloc.sell_trade_id,
                    alloc.quantity,
                    alloc.match_type,
                    alloc,
                )
            )
        sell_alloc_qtys[alloc.sell_trade_id].append(alloc.quantity)

    unsold_by_buy = {
        u["buy_trade_id"]: int(u["quantity"])
        for u in fifo.unsold_lots
        if u.get("buy_trade_id")
    }

    buy_alloc_meta: dict[str, dict[str, Any]] = {}
    buy_piece_amounts: dict[str, list[Decimal]] = {}
    for buy_id, qtys in buy_alloc_qtys.items():
        buy = by_id[buy_id]
        full_qtys = list(qtys)
        if buy_id in unsold_by_buy:
            full_qtys.append(unsold_by_buy[buy_id])
        meta = allocate_fragment_amounts(
            unit_price=buy.unit_price, gross=buy.gross_amount, qtys=full_qtys
        )
        buy_alloc_meta[buy_id] = meta
        buy_piece_amounts[buy_id] = list(meta["amounts"])

    for buy_id, qty in unsold_by_buy.items():
        if buy_id in buy_piece_amounts:
            continue
        buy = by_id[buy_id]
        meta = allocate_fragment_amounts(
            unit_price=buy.unit_price, gross=buy.gross_amount, qtys=[qty]
        )
        buy_alloc_meta[buy_id] = meta
        buy_piece_amounts[buy_id] = list(meta["amounts"])

    sell_alloc_meta: dict[str, dict[str, Any]] = {}
    sell_piece_amounts: dict[str, list[Decimal]] = {}
    for sell_id, qtys in sell_alloc_qtys.items():
        sell = by_id[sell_id]
        unmatched = int(fifo.unmatched_by_sell.get(sell_id, 0))
        full_qtys = list(qtys)
        if unmatched:
            full_qtys.append(unmatched)
        meta = allocate_fragment_amounts(
            unit_price=sell.unit_price, gross=sell.gross_amount, qtys=full_qtys
        )
        sell_alloc_meta[sell_id] = meta
        sell_piece_amounts[sell_id] = list(meta["amounts"])

    buy_fee_used: set[str] = set()
    sell_fee_used: set[str] = set()
    sell_piece_cursor: dict[str, int] = defaultdict(int)
    buy_piece_cursor: dict[str, int] = defaultdict(int)
    realized = Decimal(0)
    matched_qty = 0
    allocation_lines: list[dict[str, Any]] = []
    any_not_conserved = False
    interest_unknown = any(not t.interest_known for t in trades)

    for buy_id, sell_id, qty, match_type, alloc in buy_alloc_pairs:
        buy = by_id[buy_id]
        sell = by_id[sell_id]
        buy_gross = buy_piece_amounts[buy_id][buy_piece_cursor[buy_id]]
        buy_piece_cursor[buy_id] += 1
        sell_gross = sell_piece_amounts[sell_id][sell_piece_cursor[sell_id]]
        sell_piece_cursor[sell_id] += 1

        buy_fee = Decimal(0)
        if buy_id not in buy_fee_used:
            buy_fee = buy.commission
            buy_fee_used.add(buy_id)
        sell_fee = Decimal(0)
        sell_tax = Decimal(0)
        sell_interest = Decimal(0)
        sell_interest_applied = "0"
        if sell_id not in sell_fee_used:
            sell_fee = sell.commission
            sell_tax = sell.tax
            if sell.interest_known:
                sell_interest = sell.interest
                sell_interest_applied = _norm_dec_str(sell_interest)
            else:
                sell_interest = Decimal(0)
                sell_interest_applied = "UNKNOWN"
            sell_fee_used.add(sell_id)

        cost = buy_gross + buy_fee
        income = sell_gross - sell_fee - sell_tax - sell_interest
        pnl = income - cost
        realized += pnl
        matched_qty += qty

        buy_cons = buy_alloc_meta.get(buy_id, {})
        sell_cons = sell_alloc_meta.get(sell_id, {})
        line_ok = bool(buy_cons.get("conservation_ok", True)) and bool(
            sell_cons.get("conservation_ok", True)
        )
        if not line_ok:
            any_not_conserved = True

        allocation_lines.append(
            {
                "sequence_no": alloc.sequence_no,
                "match_type": match_type,
                "buy_trade_id": buy_id,
                "opening_lot_id": alloc.opening_lot_id,
                "sell_trade_id": sell_id,
                "quantity": qty,
                "account_id": alloc.account_id,
                "symbol": alloc.symbol,
                "currency": alloc.currency,
                "buy_gross": _norm_dec_str(buy_gross),
                "sell_gross": _norm_dec_str(sell_gross),
                "buy_commission_applied": _norm_dec_str(buy_fee),
                "sell_commission_applied": _norm_dec_str(sell_fee),
                "sell_tax_applied": _norm_dec_str(sell_tax),
                "sell_interest_applied": sell_interest_applied,
                "cost": _norm_dec_str(cost),
                "income": _norm_dec_str(income),
                "realized_pnl": _norm_dec_str(pnl),
                "gross_conservation_ok": line_ok,
                "buy_gross_difference": buy_cons.get("difference", "0"),
                "sell_gross_difference": sell_cons.get("difference", "0"),
            }
        )

    open_qty = 0
    open_cost = Decimal(0)
    for buy_id, remain_qty in unsold_by_buy.items():
        buy = by_id[buy_id]
        open_qty += remain_qty
        amounts = buy_piece_amounts[buy_id]
        if buy_id in buy_alloc_qtys:
            unsold_gross = amounts[-1]
        else:
            unsold_gross = amounts[0]
        fee = Decimal(0)
        if buy_id not in buy_fee_used:
            fee = buy.commission
            buy_fee_used.add(buy_id)
        open_cost += unsold_gross + fee
        if not buy_alloc_meta.get(buy_id, {}).get("conservation_ok", True):
            any_not_conserved = True

    status = "COMPUTED"
    if fifo.unmatched_sell_qty > 0:
        status = "PARTIAL_DUE_TO_UNMATCHED_SELLS"
    if interest_unknown:
        status = "PARTIAL_DUE_TO_UNKNOWN_INTEREST"
    if any_not_conserved:
        status = "PARTIAL_AMOUNT_NOT_CONSERVED"

    return {
        "status": status,
        "matched_allocated_qty": matched_qty,
        "realized_pnl": _norm_dec_str(realized),
        "open_quantity": open_qty,
        "open_cost": _norm_dec_str(open_cost),
        "unmatched_sell_qty": fifo.unmatched_sell_qty,
        "same_day_reconciled_qty": fifo.same_day_reconciled_qty,
        "standard_fifo_allocated_qty": fifo.standard_fifo_allocated_qty,
        "allocation_lines": allocation_lines,
        "amount_conservation_ok": not any_not_conserved,
    }


def rows_to_expected_trades(rows: Sequence[dict[str, Any]]) -> list[ExpectedTrade]:
    """將 A 有效列轉為 ExpectedTrade（trade_id＝來源識別:L列號）。"""
    trades: list[ExpectedTrade] = []
    for idx, row in enumerate(rows):
        side = str(row.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            raw = str(row.get("side_raw") or "")
            if "買" in raw:
                side = "BUY"
            elif "賣" in raw:
                side = "SELL"
            else:
                continue
        trade_date = parse_flexible_date(str(row["trade_date"]))
        if trade_date is None:
            raise ValueError(f"invalid_trade_date:{row.get('trade_date')!r}")
        physical = row.get("physical_line", idx + 1)
        source_id = str(
            row.get("source_id")
            or row.get("_year_key")
            or row.get("source_key")
            or "UNKNOWN_SOURCE"
        )
        trade_id = make_expected_trade_id(source_id, physical)

        raw_type = row.get("trade_type", None)
        if raw_type is None or str(raw_type).strip() == "":
            trade_type = "UNKNOWN"
            trade_type_known = False
        else:
            trade_type = str(raw_type).strip().upper()
            trade_type_known = trade_type in {"CASH", "DAY_TRADE"}

        raw_ccy = row.get("currency", None)
        if raw_ccy is None or str(raw_ccy).strip() == "":
            currency = "UNKNOWN"
            currency_known = False
        else:
            currency = str(raw_ccy).strip()
            currency_known = True

        interest_raw = row.get("interest", "")
        interest, interest_known = _dec_or_zero_if_explicit(interest_raw)
        account_id = str(row.get("account_id") or "default")

        trades.append(
            ExpectedTrade(
                trade_id=trade_id,
                symbol=str(row["symbol"]),
                trade_date=trade_date,
                side=side,
                quantity=int(_dec(row["quantity"])),
                unit_price=_dec(row["unit_price"]),
                gross_amount=_dec(row["gross_amount"]),
                commission=_dec(row["commission"]),
                tax=_dec(row["tax"]),
                interest=interest,
                source_order=idx,
                currency=currency,
                trade_type=trade_type if trade_type_known else "UNKNOWN",
                account_id=account_id,
                interest_known=interest_known,
                currency_known=currency_known,
                trade_type_known=trade_type_known,
            )
        )
    if not trade_ids_unique(trades):
        raise ValueError("duplicate_expected_trade_id")
    return trades


def build_expected_c_document(
    *,
    case_id: str,
    source_sha256: str,
    source_path: str,
    source_format: str,
    applicable_spec: Sequence[str],
    rows: Sequence[dict[str, Any]],
    opening_lots_policy: str = "NONE_APPROVED",
    opening_lots: Iterable[ExpectedOpeningLot] = (),
    extra_fields_not_computable: Sequence[str] | None = None,
    known_limitations: Sequence[str] | None = None,
    expected_source_sha256: dict[str, str] | None = None,
    actual_source_sha256: dict[str, str] | None = None,
    invalid_row_count: int | str | None = 0,
) -> dict[str, Any]:
    """組裝可存檔之獨立 C 層文件（含逐筆 allocation；不含受測系統輸出）。"""
    openings = list(opening_lots)
    if opening_lots_policy != "NONE_APPROVED" and not openings:
        raise ValueError("opening_lots_policy requires approved lots")
    if opening_lots_policy == "NONE_APPROVED" and openings:
        raise ValueError("NONE_APPROVED cannot include opening lots")

    integrity = evaluate_source_integrity(
        expected_sha256=expected_source_sha256 or {},
        actual_sha256=actual_source_sha256 or {},
        invalid_row_count=invalid_row_count,
    )
    # 未提供指紋鎖定時不因空 dict 誤判 PASS 掩蓋；呼叫端應傳入
    if expected_source_sha256 is None and actual_source_sha256 is None:
        integrity = {
            "status": "SKIPPED_NO_LOCK_PROVIDED",
            "reasons": ["source_sha256_lock_not_provided"],
            "sha256_mismatches": [],
        }

    aggregates = aggregate_source_finance(rows)
    trades = rows_to_expected_trades(rows)
    non_cash = [t for t in trades if t.trade_type_known and t.trade_type != "CASH"]
    unknown_type = [t for t in trades if not t.trade_type_known]
    unknown_ccy = [t for t in trades if not t.currency_known]
    cash_trades = [
        t
        for t in trades
        if t.trade_type_known and t.trade_type == "CASH" and t.currency_known
    ]
    fifo = independent_cash_fifo(cash_trades, opening_lots=openings)
    finance = compute_realized_and_open(cash_trades, fifo)

    not_computable = list(extra_fields_not_computable or [])
    if non_cash or unknown_type:
        not_computable.append("DAY_TRADE_OR_UNKNOWN_TYPE_NOT_IN_CASH_FIFO")
    if unknown_ccy:
        not_computable.append("unknown_currency_rows")
    if not aggregates.get("interest_known", True):
        not_computable.append("interest_blank_rows")

    limitations = list(known_limitations or [])
    limitations.append("C 由 A＋SPEC 獨立推導；未使用受測 FIFO／Report Projector／新版 Excel")
    limitations.append("fifo_scope=CASH_ONLY；DAY_TRADE 未納入本 C 層配對")
    if opening_lots_policy == "NONE_APPROVED":
        limitations.append("無核准期初 lot；不得偽造期初庫存")

    if integrity["status"] == "FAIL":
        validation_status = "BLOCKED_SOURCE_INTEGRITY"
    elif (
        integrity["status"] == "PARTIAL"
        or finance["status"] != "COMPUTED"
        or unknown_ccy
        or unknown_type
        or non_cash
    ):
        validation_status = "INDEPENDENTLY_COMPUTED_PARTIAL"
    else:
        validation_status = "INDEPENDENTLY_COMPUTED"

    allocations_out = [
        {
            "sequence_no": a.sequence_no,
            "match_type": a.match_type,
            "buy_trade_id": a.buy_trade_id,
            "opening_lot_id": a.opening_lot_id,
            "sell_trade_id": a.sell_trade_id,
            "quantity": a.quantity,
            "account_id": a.account_id,
            "symbol": a.symbol,
            "currency": a.currency,
        }
        for a in fifo.allocations
    ]

    return {
        "case_id": case_id,
        "layer": "C",
        "derivation": "A_source_plus_SPEC",
        "source_path": source_path,
        "source_format": source_format,
        "source_sha256": source_sha256,
        "applicable_spec": list(applicable_spec),
        "opening_lots": opening_lots_policy,
        "invalid_row_count_status": invalid_row_count_status(source_format),
        "invalid_row_count": invalid_row_count,
        "source_integrity": integrity,
        "validation_status": validation_status,
        "fifo_scope": "CASH_ONLY",
        "aggregates": aggregates,
        "fifo_expected": {
            "algorithm": "CASH_TWO_PASS_SPEC_INDEPENDENT",
            "pool_key": "account_id+symbol+currency+CASH",
            "standard_fifo_allocated_qty": fifo.standard_fifo_allocated_qty,
            "same_day_reconciled_qty": fifo.same_day_reconciled_qty,
            "unmatched_sell_qty": fifo.unmatched_sell_qty,
            "unsold_buy_qty": fifo.unsold_buy_qty,
            "blocking_insufficient_prior_buys": fifo.blocking_insufficient_prior_buys,
            "allocation_count": len(fifo.allocations),
        },
        "allocations": allocations_out,
        "allocation_lines": finance.get("allocation_lines", []),
        "realized_and_open": {
            k: v for k, v in finance.items() if k != "allocation_lines"
        },
        "trade_id_unique": trade_ids_unique(trades),
        "trade_count": len(trades),
        "trade_fingerprints": [
            {
                "source_trade_id": t.trade_id,
                "symbol": t.symbol,
                "trade_date": t.trade_date.isoformat(),
                "side": t.side,
                "quantity": t.quantity,
                "unit_price": str(t.unit_price),
                "gross_amount": str(t.gross_amount),
                "commission": str(t.commission),
                "tax": str(t.tax),
                "interest": str(t.interest) if t.interest_known else "",
            }
            for t in trades
        ],
        "fields_not_computable": not_computable,
        "known_limitations": limitations,
    }
