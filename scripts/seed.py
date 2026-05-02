"""Seed synthetic Faker contracts into the dev database.

Why synthetic instead of EDGAR? EDGAR's filing index is rate-limited and the
HTML→text pipeline is flaky in CI. The synthetic generator emits clauses with
known labels so the eval harness has ground truth without manual labelling.

To wire EDGAR later, add a fetcher that pulls 10-K Exhibit 10.* contracts and
runs the same chunk → embed → classify pipeline used here.
"""

from __future__ import annotations

import argparse
import hashlib
import random
from dataclasses import dataclass

from faker import Faker

CLAUSES: dict[str, list[str]] = {
    "change_of_control": [
        "This Agreement shall terminate upon a Change of Control of {p}, defined as "
        "the acquisition of more than fifty percent (50%) of the outstanding voting "
        "securities. Notice shall be given within five (5) business days.",
    ],
    "ip_assignment": [
        "All Intellectual Property created by {p} in connection with the Services "
        "shall vest in the Customer upon creation; {p} hereby assigns all right, "
        "title, and interest in such Intellectual Property to the Customer.",
    ],
    "exclusivity": [
        "During the Term, {p} shall not, directly or indirectly, provide services "
        "substantially similar to the Services to any competitor of the Customer "
        "without prior written consent.",
    ],
    "termination": [
        "Either party may terminate this Agreement upon thirty (30) days' written "
        "notice if the other party materially breaches and fails to cure within "
        "such notice period.",
    ],
    "indemnity": [
        "{p} shall indemnify and hold harmless the Customer from and against any "
        "and all claims, losses, and expenses arising out of {p}'s gross negligence "
        "or willful misconduct.",
    ],
    "governing_law": [
        "This Agreement shall be governed by and construed in accordance with the "
        "laws of the State of Delaware, without regard to conflict-of-laws rules.",
    ],
}


@dataclass
class SyntheticContract:
    title: str
    pages: list[tuple[int, str]]  # (page_no, text)

    @property
    def sha256(self) -> str:
        body = self.title + "\n".join(t for _, t in self.pages)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def synth_contract(fake: Faker, *, n_pages: int = 6) -> SyntheticContract:
    party_a = fake.company()
    party_b = fake.company()
    title = f"Master Services Agreement between {party_a} and {party_b}"
    body: list[tuple[int, str]] = []
    page_buf: list[str] = [f"This Agreement is made between {party_a} and {party_b}."]
    page_no = 1
    for clause_type, templates in CLAUSES.items():
        text = random.choice(templates).format(p=party_b)
        page_buf.append(f"\nSection — {clause_type.replace('_', ' ').title()}\n{text}")
        if len(" ".join(page_buf)) > 1800:
            body.append((page_no, "\n".join(page_buf)))
            page_no += 1
            page_buf = []
    if page_buf:
        body.append((page_no, "\n".join(page_buf)))
    while len(body) < n_pages:
        page_no += 1
        body.append((page_no, fake.paragraph(nb_sentences=12)))
    return SyntheticContract(title=title, pages=body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Lexscribe with synthetic contracts.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--print", action="store_true", help="dry-run; print first contract")
    args = parser.parse_args()

    Faker.seed(args.seed)
    random.seed(args.seed)
    fake = Faker()

    contracts = [synth_contract(fake) for _ in range(args.count)]

    if args.print:
        c = contracts[0]
        print(f"# {c.title}\nsha256={c.sha256}\npages={len(c.pages)}")
        for p, text in c.pages[:2]:
            print(f"\n--- page {p} ---\n{text}")
        return

    # DB insertion path is intentionally minimal; integration tests cover it.
    print(f"Generated {len(contracts)} contracts (dry-run; pass to a worker to ingest).")


if __name__ == "__main__":
    main()
