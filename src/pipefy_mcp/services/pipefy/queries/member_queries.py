"""GraphQL mutations for pipe member management.

InviteMembersInput: pipe_id, emails (list of { email, role_name }).
RemoveMembersFromPipeInput: pipeUuid, usersUuids (or groupsUuids).
SetRoleInput: pipe_id, member { user_id, role_name }.
"""

from __future__ import annotations

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.
# Input shapes verified via introspect_mutation / deep-mutation (inviteMembers, removeMembersFromPipe, setRole).

INVITE_MEMBERS_MUTATION = gql(
    """
    mutation InviteMembers($input: InviteMembersInput!) {
        inviteMembers(input: $input) {
            users {
                id
                email
            }
            errors
        }
    }
    """
)

REMOVE_MEMBERS_FROM_PIPE_MUTATION = gql(
    """
    mutation RemoveMembersFromPipe($input: RemoveMembersFromPipeInput!) {
        removeMembersFromPipe(input: $input) {
            success
            removedUsersUuids
            removedGroupsUuids
            errors
        }
    }
    """
)

SET_ROLE_MUTATION = gql(
    """
    mutation SetRole($input: SetRoleInput!) {
        setRole(input: $input) {
            member {
                role_name
                user {
                    id
                    email
                }
            }
        }
    }
    """
)

__all__ = [
    "INVITE_MEMBERS_MUTATION",
    "REMOVE_MEMBERS_FROM_PIPE_MUTATION",
    "SET_ROLE_MUTATION",
]
