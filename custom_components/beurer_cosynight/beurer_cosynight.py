import dataclasses
import datetime
import json
import logging
import os
import requests


_BASE_URL = 'https://cosynight.azurewebsites.net'
_DATETIME_FORMAT = '%a, %d %b %Y %H:%M:%S %Z'
_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Device:
    active: bool
    id: str
    name: str
    requiresUpdate: bool


@dataclasses.dataclass
class Quickstart:
    bodySetting: int
    feetSetting: int
    id: str
    timespan: int  # Seconds


@dataclasses.dataclass
class Status:
    active: bool
    bodySetting: int
    feetSetting: int
    heartbeat: int
    id: str
    name: str
    requiresUpdate: bool
    timer: int


@dataclasses.dataclass
class _Token:
    access_token: str
    expires: str
    expires_in: int
    issued: str
    refresh_token: str
    token_type: str
    user_email: str
    user_id: str


class _TokenAuth(requests.auth.AuthBase):

    def __init__(self, token):
        self._token = token

    def __call__(self, request):
        request.headers['Authorization'] = (
                f'{self._token.token_type} {self._token.access_token}')
        return request


class BeurerCosyNight:

    class Error(Exception):
        pass

    class AuthenticationError(Error):
        """Raised when authentication fails (e.g., 401 Unauthorized)."""
        pass

    def _check_response_auth(self, response):
        """Check response for authentication errors and raise AuthenticationError if needed."""
        if response.status_code == 401:
            self._token = None  # Clear invalid token
            raise self.AuthenticationError(
                f"Authentication failed: {response.status_code} {response.reason} for url: {response.url}"
            )

    def __init__(self, token_path: str = None):
        self._token = None
        self._token_path = token_path or 'token'
        # Don't load token in __init__ - defer to first use
        self._token_loaded = False

    def _load_token(self):
        """Load token from file if not already loaded."""
        if self._token_loaded:
            return
        
        self._token_loaded = True
        if os.path.exists(self._token_path):
            try:
                with open(self._token_path) as f:
                    self._token = _Token(**json.load(f))
                _LOGGER.debug("Token loaded from %s", self._token_path)
            except Exception as e:
                _LOGGER.error("Failed to load token: %s", e)

    def _update_token(self, response):
        body = response.json()
        body['expires'] = body.pop('.expires')
        body['issued'] = body.pop('.issued')
        self._token = _Token(**body)
        try:
            with open(self._token_path, 'w') as f:
                json.dump(dataclasses.asdict(self._token), f)
            _LOGGER.debug("Token updated and saved to %s", self._token_path)
        except Exception as e:
            _LOGGER.error("Failed to save token: %s", e)

    def _refresh_token(self):
        self._load_token()
        
        if self._token is None:
            raise self.Error('Not authenticated')

        expires = datetime.datetime.strptime(self._token.expires, _DATETIME_FORMAT)
        expires = expires.replace(tzinfo=datetime.timezone.utc)
        if datetime.datetime.now(datetime.timezone.utc) > expires:
            _LOGGER.debug('Refreshing token...')
            r = requests.post(_BASE_URL + '/token',
                              data={
                                  'grant_type': 'refresh_token',
                                  'refresh_token': self._token.refresh_token 
                              })
            if r.status_code == requests.codes.ok:
                self._update_token(r)
            elif r.status_code == 401:
                self._token = None
                raise self.AuthenticationError(
                    "Token refresh failed: credentials may have changed or expired"
                )
            else:
                self._token = None
                r.raise_for_status()

    def authenticate(self, username, password):
        self._load_token()
        
        if self._token is None:
            _LOGGER.info('Requesting new token for user %s...', username)
            r = requests.post(_BASE_URL + '/token',
                              data={
                                  'grant_type': 'password',
                                  'username': username,
                                  'password': password
                              })
            if r.status_code == 401:
                raise self.AuthenticationError(
                    "Authentication failed: invalid username or password"
                )
            r.raise_for_status()
            self._update_token(r)
            _LOGGER.info('Authentication successful')
        else:
            self._refresh_token()

    def get_status(self, id):
        self._refresh_token()
        _LOGGER.debug('Getting device status for device %s...', id)
        r = requests.post(_BASE_URL + '/api/v1/Device/GetStatus',
                          json={'id': id},
                          auth=_TokenAuth(self._token))
        self._check_response_auth(r)
        r.raise_for_status()
        body = r.json()
        body['requiresUpdate'] = body.pop('requieresUpdate')
        return Status(**body)
 
    def list_devices(self):
        self._refresh_token()
        _LOGGER.debug('Listing devices...')
        r = requests.get(_BASE_URL + '/api/v1/Device/List', auth=_TokenAuth(self._token))
        self._check_response_auth(r)
        r.raise_for_status()
        devices = r.json().get('devices', [])
        _LOGGER.info('Found %d device(s)', len(devices))
        ds = []
        for d in devices:
            d['requiresUpdate'] = d.pop('requieresUpdate')
            ds.append(Device(**d))
        return ds
 
    def quickstart(self, quickstart):
        self._refresh_token()
        _LOGGER.debug('Quick starting device...')
        r = requests.post(_BASE_URL + '/api/v1/Device/Quickstart',
                          json=dataclasses.asdict(quickstart),
                          auth=_TokenAuth(self._token))
        self._check_response_auth(r)
        r.raise_for_status()

