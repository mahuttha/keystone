# Copyright 2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_log import log
from oslo_utils import encodeutils
import six

import keystone.conf
from keystone.i18n import _, _LW


CONF = keystone.conf.CONF
LOG = log.getLogger(__name__)

# Tests use this to make exception message format errors fatal
_FATAL_EXCEPTION_FORMAT_ERRORS = False


def _format_with_unicode_kwargs(msg_format, kwargs):
    try:
        return msg_format % kwargs
    except UnicodeDecodeError:
        try:
            kwargs = {k: encodeutils.safe_decode(v)
                      for k, v in kwargs.items()}
        except UnicodeDecodeError:
            # NOTE(jamielennox): This is the complete failure case
            # at least by showing the template we have some idea
            # of where the error is coming from
            return msg_format

        return msg_format % kwargs


class Error(Exception):
    """Base error class.

    Child classes should define an HTTP status code, title, and a
    message_format.

    """

    code = None
    title = None
    message_format = None

    def __init__(self, message=None, **kwargs):
        try:
            message = self._build_message(message, **kwargs)
        except KeyError:
            # if you see this warning in your logs, please raise a bug report
            if _FATAL_EXCEPTION_FORMAT_ERRORS:
                raise
            else:
                LOG.warning(_LW('missing exception kwargs (programmer error)'))
                message = self.message_format

        super(Error, self).__init__(message)

    def _build_message(self, message, **kwargs):
        """Build and returns an exception message.

        :raises KeyError: given insufficient kwargs

        """
        if message:
            return message
        return _format_with_unicode_kwargs(self.message_format, kwargs)


class ValidationError(Error):
    message_format = _("Expecting to find %(attribute)s in %(target)s -"
                       " the server could not comply with the request"
                       " since it is either malformed or otherwise"
                       " incorrect. The client is assumed to be in error.")
    code = 400
    title = 'Bad Request'


class URLValidationError(ValidationError):
    message_format = _("Cannot create an endpoint with an invalid URL:"
                       " %(url)s")


class PasswordValidationError(ValidationError):
    message_format = _("Password validation error: %(detail)s")


class PasswordAgeValidationError(PasswordValidationError):
    message_format = _("You cannot change your password at this time due "
                       "to the minimum password age. Once you change your "
                       "password, it must be used for %(min_age_days)d day(s) "
                       "before it can be changed. Please try again in "
                       "%(days_left)d day(s) or contact your administrator to "
                       "reset your password.")


class SchemaValidationError(ValidationError):
    # NOTE(lbragstad): For whole OpenStack message consistency, this error
    # message has been written in a format consistent with WSME.
    message_format = _("%(detail)s")


class ValidationTimeStampError(Error):
    message_format = _("Timestamp not in expected format."
                       " The server could not comply with the request"
                       " since it is either malformed or otherwise"
                       " incorrect. The client is assumed to be in error.")
    code = 400
    title = 'Bad Request'


class ValidationExpirationError(Error):
    message_format = _("The 'expires_at' must not be before now."
                       " The server could not comply with the request"
                       " since it is either malformed or otherwise"
                       " incorrect. The client is assumed to be in error.")
    code = 400
    title = 'Bad Request'


class StringLengthExceeded(ValidationError):
    message_format = _("String length exceeded.The length of"
                       " string '%(string)s' exceeded the limit"
                       " of column %(type)s(CHAR(%(length)d)).")


class ValidationSizeError(Error):
    message_format = _("Request attribute %(attribute)s must be"
                       " less than or equal to %(size)i. The server"
                       " could not comply with the request because"
                       " the attribute size is invalid (too large)."
                       " The client is assumed to be in error.")
    code = 400
    title = 'Bad Request'


class CircularRegionHierarchyError(Error):
    message_format = _("The specified parent region %(parent_region_id)s "
                       "would create a circular region hierarchy.")
    code = 400
    title = 'Bad Request'


class ForbiddenNotSecurity(Error):
    """When you want to return a 403 Forbidden response but not security.

    Use this for errors where the message is always safe to present to the user
    and won't give away extra information.

    """

    code = 403
    title = 'Forbidden'


class PasswordVerificationError(ForbiddenNotSecurity):
    message_format = _("The password length must be less than or equal "
                       "to %(size)i. The server could not comply with the "
                       "request because the password is invalid.")


class RegionDeletionError(ForbiddenNotSecurity):
    message_format = _("Unable to delete region %(region_id)s because it or "
                       "its child regions have associated endpoints.")


class PKITokenExpected(ForbiddenNotSecurity):
    message_format = _('The certificates you requested are not available. '
                       'It is likely that this server does not use PKI tokens '
                       'otherwise this is the result of misconfiguration.')


class SecurityError(Error):
    """Security error exception.

    Avoids exposing details of security errors, unless in insecure_debug mode.

    """

    amendment = _('(Disable insecure_debug mode to suppress these details.)')

    def __deepcopy__(self):
        """Override the default deepcopy.

        Keystone :class:`keystone.exception.Error` accepts an optional message
        that will be used when rendering the exception object as a string. If
        not provided the object's message_format attribute is used instead.
        :class:`keystone.exception.SecurityError` is a little different in
        that it only uses the message provided to the initializer when
        keystone is in `insecure_debug` mode. Instead it will use its
        `message_format`. This is to ensure that sensitive details are not
        leaked back to the caller in a production deployment.

        This dual mode for string rendering causes some odd behaviour when
        combined with oslo_i18n translation. Any object used as a value for
        formatting a translated string is deep copied.

        The copy causes an issue. The deep copy process actually creates a new
        exception instance with the rendered string. Then when that new
        instance is rendered as a string to use for substitution a warning is
        logged. This is because the code tries to use the `message_format` in
        secure mode, but the required kwargs are not in the deep copy.

        The end result is not an error because when the KeyError is caught the
        instance's ``message`` is used instead and this has the properly
        translated message. The only indication that something is wonky is a
        message in the warning log.
        """
        return self

    def _build_message(self, message, **kwargs):
        """Only returns detailed messages in insecure_debug mode."""
        if message and CONF.insecure_debug:
            if isinstance(message, six.string_types):
                # Only do replacement if message is string. The message is
                # sometimes a different exception or bytes, which would raise
                # TypeError.
                message = _format_with_unicode_kwargs(message, kwargs)
            return _('%(message)s %(amendment)s') % {
                'message': message,
                'amendment': self.amendment}

        return _format_with_unicode_kwargs(self.message_format, kwargs)


class Unauthorized(SecurityError):
    message_format = _("The request you have made requires authentication.")
    code = 401
    title = 'Unauthorized'


class PasswordExpired(Unauthorized):
    message_format = _("The password is expired and needs to be reset by an "
                       "administrator for user: %(user_id)s")


class AuthPluginException(Unauthorized):
    message_format = _("Authentication plugin error.")

    def __init__(self, *args, **kwargs):
        super(AuthPluginException, self).__init__(*args, **kwargs)
        self.authentication = {}


class MissingGroups(Unauthorized):
    message_format = _("Unable to find valid groups while using "
                       "mapping %(mapping_id)s")


class UserDisabled(Unauthorized):
    message_format = _("The account is disabled for user: %(user_id)s")


class AccountLocked(Unauthorized):
    message_format = _("The account is locked for user: %(user_id)s")


class AuthMethodNotSupported(AuthPluginException):
    message_format = _("Attempted to authenticate with an unsupported method.")

    def __init__(self, *args, **kwargs):
        super(AuthMethodNotSupported, self).__init__(*args, **kwargs)
        self.authentication = {'methods': CONF.auth.methods}


class AdditionalAuthRequired(AuthPluginException):
    message_format = _("Additional authentications steps required.")

    def __init__(self, auth_response=None, **kwargs):
        super(AdditionalAuthRequired, self).__init__(message=None, **kwargs)
        self.authentication = auth_response


class Forbidden(SecurityError):
    message_format = _("You are not authorized to perform the"
                       " requested action.")
    code = 403
    title = 'Forbidden'


class ForbiddenAction(Forbidden):
    message_format = _("You are not authorized to perform the"
                       " requested action: %(action)s")


class ImmutableAttributeError(Forbidden):
    message_format = _("Could not change immutable attribute(s) "
                       "'%(attributes)s' in target %(target)s")


class CrossBackendNotAllowed(Forbidden):
    message_format = _("Group membership across backend boundaries is not "
                       "allowed, group in question is %(group_id)s, "
                       "user is %(user_id)s")


class InvalidPolicyAssociation(Forbidden):
    message_format = _("Invalid mix of entities for policy association - "
                       "only Endpoint, Service or Region+Service allowed. "
                       "Request was - Endpoint: %(endpoint_id)s, "
                       "Service: %(service_id)s, Region: %(region_id)s")


class InvalidDomainConfig(Forbidden):
    message_format = _("Invalid domain specific configuration: %(reason)s")


class NotFound(Error):
    message_format = _("Could not find: %(target)s")
    code = 404
    title = 'Not Found'


class EndpointNotFound(NotFound):
    message_format = _("Could not find endpoint: %(endpoint_id)s")


class MetadataNotFound(NotFound):
    # NOTE (dolph): metadata is not a user-facing concept,
    # so this exception should not be exposed.

    message_format = _("An unhandled exception has occurred:"
                       " Could not find metadata.")


class PolicyNotFound(NotFound):
    message_format = _("Could not find policy: %(policy_id)s")


class PolicyAssociationNotFound(NotFound):
    message_format = _("Could not find policy association")


class RoleNotFound(NotFound):
    message_format = _("Could not find role: %(role_id)s")


class ImpliedRoleNotFound(NotFound):
    message_format = _("%(prior_role_id)s does not imply %(implied_role_id)s")


class InvalidImpliedRole(Forbidden):
    message_format = _("%(role_id)s cannot be an implied roles")


class RoleAssignmentNotFound(NotFound):
    message_format = _("Could not find role assignment with role: "
                       "%(role_id)s, user or group: %(actor_id)s, "
                       "project or domain: %(target_id)s")


class RegionNotFound(NotFound):
    message_format = _("Could not find region: %(region_id)s")


class ServiceNotFound(NotFound):
    message_format = _("Could not find service: %(service_id)s")


class DomainNotFound(NotFound):
    message_format = _("Could not find domain: %(domain_id)s")


class ProjectNotFound(NotFound):
    message_format = _("Could not find project: %(project_id)s")


class InvalidParentProject(NotFound):
    message_format = _("Cannot create project with parent: %(project_id)s")


class TokenNotFound(NotFound):
    message_format = _("Could not find token: %(token_id)s")


class UserNotFound(NotFound):
    message_format = _("Could not find user: %(user_id)s")


class GroupNotFound(NotFound):
    message_format = _("Could not find group: %(group_id)s")


class MappingNotFound(NotFound):
    message_format = _("Could not find mapping: %(mapping_id)s")


class TrustNotFound(NotFound):
    message_format = _("Could not find trust: %(trust_id)s")


class TrustUseLimitReached(Forbidden):
    message_format = _("No remaining uses for trust: %(trust_id)s")


class CredentialNotFound(NotFound):
    message_format = _("Could not find credential: %(credential_id)s")


class VersionNotFound(NotFound):
    message_format = _("Could not find version: %(version)s")


class EndpointGroupNotFound(NotFound):
    message_format = _("Could not find Endpoint Group: %(endpoint_group_id)s")


class IdentityProviderNotFound(NotFound):
    message_format = _("Could not find Identity Provider: %(idp_id)s")


class ServiceProviderNotFound(NotFound):
    message_format = _("Could not find Service Provider: %(sp_id)s")


class FederatedProtocolNotFound(NotFound):
    message_format = _("Could not find federated protocol %(protocol_id)s for"
                       " Identity Provider: %(idp_id)s")


class PublicIDNotFound(NotFound):
    # This is used internally and mapped to either User/GroupNotFound or,
    # Assertion before the exception leaves Keystone.
    message_format = "%(id)s"


class DomainConfigNotFound(NotFound):
    message_format = _('Could not find %(group_or_option)s in domain '
                       'configuration for domain %(domain_id)s')


class ConfigRegistrationNotFound(Exception):
    # This is used internally between the domain config backend and the
    # manager, so should not escape to the client.  If it did, it is a coding
    # error on our part, and would end up, appropriately, as a 500 error.
    pass


class KeystoneConfigurationError(Exception):
    # This is an exception to be used in the case that Keystone config is
    # invalid and Keystone should not start.
    pass


class Conflict(Error):
    message_format = _("Conflict occurred attempting to store %(type)s -"
                       " %(details)s")
    code = 409
    title = 'Conflict'


class UnexpectedError(SecurityError):
    """Avoids exposing details of failures, unless in insecure_debug mode."""

    message_format = _("An unexpected error prevented the server "
                       "from fulfilling your request.")

    debug_message_format = _("An unexpected error prevented the server "
                             "from fulfilling your request: %(exception)s")

    def _build_message(self, message, **kwargs):

        # Ensure that exception has a value to be extra defensive for
        # substitutions and make sure the exception doesn't raise an
        # exception.
        kwargs.setdefault('exception', '')

        return super(UnexpectedError, self)._build_message(
            message or self.debug_message_format, **kwargs)

    code = 500
    title = 'Internal Server Error'


class TrustConsumeMaximumAttempt(UnexpectedError):
    debug_message_format = _("Unable to consume trust %(trust_id)s, unable to "
                             "acquire lock.")


class CertificateFilesUnavailable(UnexpectedError):
    debug_message_format = _("Expected signing certificates are not available "
                             "on the server. Please check Keystone "
                             "configuration.")


class MalformedEndpoint(UnexpectedError):
    debug_message_format = _("Malformed endpoint URL (%(endpoint)s),"
                             " see ERROR log for details.")


class MappedGroupNotFound(UnexpectedError):
    debug_message_format = _("Group %(group_id)s returned by mapping "
                             "%(mapping_id)s was not found in the backend.")


class MetadataFileError(UnexpectedError):
    debug_message_format = _("Error while reading metadata file, %(reason)s")


class DirectMappingError(UnexpectedError):
    message_format = _("Local section in mapping %(mapping_id)s refers to a "
                       "remote match that doesn't exist "
                       "(e.g. {0} in a local section).")


class AssignmentTypeCalculationError(UnexpectedError):
    debug_message_format = _(
        'Unexpected combination of grant attributes - '
        'User: %(user_id)s, Group: %(group_id)s, Project: %(project_id)s, '
        'Domain: %(domain_id)s')


class NotImplemented(Error):
    message_format = _("The action you have requested has not"
                       " been implemented.")
    code = 501
    title = 'Not Implemented'


class Gone(Error):
    message_format = _("The service you have requested is no"
                       " longer available on this server.")
    code = 410
    title = 'Gone'


class ConfigFileNotFound(UnexpectedError):
    debug_message_format = _("The Keystone configuration file %(config_file)s "
                             "could not be found.")


class KeysNotFound(UnexpectedError):
    debug_message_format = _('No encryption keys found; run keystone-manage '
                             'fernet_setup to bootstrap one.')


class MultipleSQLDriversInConfig(UnexpectedError):
    debug_message_format = _('The Keystone domain-specific configuration has '
                             'specified more than one SQL driver (only one is '
                             'permitted): %(source)s.')


class MigrationNotProvided(Exception):
    def __init__(self, mod_name, path):
        super(MigrationNotProvided, self).__init__(_(
            "%(mod_name)s doesn't provide database migrations. The migration"
            " repository path at %(path)s doesn't exist or isn't a directory."
        ) % {'mod_name': mod_name, 'path': path})


class UnsupportedTokenVersionException(UnexpectedError):
    debug_message_format = _('Token version is unrecognizable or '
                             'unsupported.')


class SAMLSigningError(UnexpectedError):
    debug_message_format = _('Unable to sign SAML assertion. It is likely '
                             'that this server does not have xmlsec1 '
                             'installed, or this is the result of '
                             'misconfiguration. Reason %(reason)s')


class OAuthHeadersMissingError(UnexpectedError):
    debug_message_format = _('No Authorization headers found, cannot proceed '
                             'with OAuth related calls, if running under '
                             'HTTPd or Apache, ensure WSGIPassAuthorization '
                             'is set to On.')


class TokenlessAuthConfigError(ValidationError):
    message_format = _('Could not determine Identity Provider ID. The '
                       'configuration option %(issuer_attribute)s '
                       'was not found in the request environment.')


class UnsupportedDriverVersion(UnexpectedError):
    debug_message_format = _('%(driver)s is not supported driver version')


class CredentialEncryptionError(Exception):
    message_format = _("An unexpected error prevented the server "
                       "from accessing encrypted credentials.")
