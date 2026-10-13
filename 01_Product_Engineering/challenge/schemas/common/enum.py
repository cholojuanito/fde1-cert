from enum import StrEnum

class State(StrEnum):
    utah = 'UT'
    delaware = 'DE'

class EntityCode(StrEnum):
    individual = "I"
    corporation = "C"
    s_corp = "S"
    nonprofit = "N"
    general_partnership = "P"
    limited_partnership = "L"
    llc = "B"
    trust = "T"
    llp = "R"
    other = "O"
