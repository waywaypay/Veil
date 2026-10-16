"""veil: reversible placeholders for personal information in what you send a model.

    from veil import Redactor
    from veil.profiles import FINANCE

    r = Redactor(FINANCE)
    r.add_person("Avery K. Mockridge")
    safe = r.redact_text("Wire to Avery Mockridge, SSN 123-45-6789")   # "Wire to NAME_001, SSN SSN_001"
    r.restore_text("Done: NAME_001's distribution.")                    # "Done: Avery K. Mockridge's distribution."
"""

from veil.profiles import FINANCE, GENERIC, PROFILES, US_TAX_K1, Profile
from veil.redactor import Redactor
from veil.tax_ids import KINDS, TAX_ID_KINDS, TaxIdRedactor

__all__ = ["Redactor", "TaxIdRedactor", "Profile", "GENERIC", "FINANCE", "US_TAX_K1", "PROFILES", "KINDS",
           "TAX_ID_KINDS"]
__version__ = "0.1.0"
