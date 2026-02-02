"""GraphQL query and mutation definitions for the Pipefy services.

This package must contain only query/mutation constants (no runtime logic).
"""

from .card_queries import (
    CREATE_CARD_MUTATION,
    GET_CARD_QUERY,
    GET_CARDS_QUERY,
    GET_CARDS_WITH_FIELDS_QUERY,
    MOVE_CARD_TO_PHASE_MUTATION,
    UPDATE_CARD_FIELD_MUTATION,
    UPDATE_CARD_MUTATION,
    UPDATE_FIELDS_VALUES_MUTATION,
)
from .pipe_queries import GET_PIPE_QUERY, GET_START_FORM_FIELDS_QUERY

__all__ = [
    "GET_PIPE_QUERY",
    "GET_START_FORM_FIELDS_QUERY",
    "CREATE_CARD_MUTATION",
    "GET_CARD_QUERY",
    "GET_CARDS_QUERY",
    "GET_CARDS_WITH_FIELDS_QUERY",
    "MOVE_CARD_TO_PHASE_MUTATION",
    "UPDATE_CARD_FIELD_MUTATION",
    "UPDATE_CARD_MUTATION",
    "UPDATE_FIELDS_VALUES_MUTATION",
]
