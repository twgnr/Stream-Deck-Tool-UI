#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from __future__ import print_function
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import comtypes
from comtypes import GUID, IUnknown, COMMETHOD, CLSCTX_ALL
from ctypes import (
    cast, POINTER, HRESULT, c_int, c_uint, c_wchar_p, c_void_p
)

#--------------------------------------------------------------------
# COM interface for the (undocumented) Windows PolicyConfig API.
# Used to change the system default audio endpoint.
#--------------------------------------------------------------------
class IPolicyConfig(IUnknown):
    _iid_ = GUID('{F8679F50-850A-41CF-9C72-430F290290C8}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetMixFormat',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'ppFormat')),
        COMMETHOD([], HRESULT, 'GetDeviceFormat',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_int, 'bDefault'),
                  (['in'], c_void_p, 'ppFormat')),
        COMMETHOD([], HRESULT, 'ResetDeviceFormat',
                  (['in'], c_wchar_p, 'wszDeviceName')),
        COMMETHOD([], HRESULT, 'SetDeviceFormat',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'pEndpointFormat'),
                  (['in'], c_void_p, 'pMixFormat')),
        COMMETHOD([], HRESULT, 'GetProcessingPeriod',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_int, 'bDefault'),
                  (['in'], c_void_p, 'pmftDefaultPeriod'),
                  (['in'], c_void_p, 'pmftMinimumPeriod')),
        COMMETHOD([], HRESULT, 'SetProcessingPeriod',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'pmftPeriod')),
        COMMETHOD([], HRESULT, 'GetShareMode',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'pMode')),
        COMMETHOD([], HRESULT, 'SetShareMode',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'pMode')),
        COMMETHOD([], HRESULT, 'GetPropertyValue',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'key'),
                  (['in'], c_void_p, 'pv')),
        COMMETHOD([], HRESULT, 'SetPropertyValue',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_void_p, 'key'),
                  (['in'], c_void_p, 'pv')),
        COMMETHOD([], HRESULT, 'SetDefaultEndpoint',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_uint, 'eRole')),
        COMMETHOD([], HRESULT, 'SetEndpointVisibility',
                  (['in'], c_wchar_p, 'wszDeviceName'),
                  (['in'], c_int, 'bVisible')),
    ]


CLSID_PolicyConfigClient = GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}')
DEVICE_STATE_ACTIVE = 0x1


def _get_active_devices():
    """Returns all currently active audio endpoints."""
    devices = AudioUtilities.GetAllDevices()
    return [d for d in devices if getattr(d, "state", 0) == DEVICE_STATE_ACTIVE and d.FriendlyName]


def list_audio_devices():
    """Lists all active audio playback devices."""
    return [d.FriendlyName for d in _get_active_devices()]


def set_default_audio_device(device_name):
    """
    Sets the default audio playback device.
    Args:
        device_name (str): A unique part of the desired device's name.

    Returns:
        str: An error message if something fails, otherwise None.
    """
    try:
        target_device = None
        for device in _get_active_devices():
            if device_name.lower() in device.FriendlyName.lower():
                target_device = device
                break

        if not target_device:
            return f"Audio device like '{device_name}' not found."

        policy_config = comtypes.CoCreateInstance(
            CLSID_PolicyConfigClient, IPolicyConfig, CLSCTX_ALL
        )

        # Role 0: eConsole (Games, System Notifications)
        # Role 1: eMultimedia (Music, Videos, etc.)
        # Role 2: eCommunications (Voice chat)
        policy_config.SetDefaultEndpoint(target_device.id, 0)
        policy_config.SetDefaultEndpoint(target_device.id, 1)
        policy_config.SetDefaultEndpoint(target_device.id, 2)

        print(f"Set default audio device to: {target_device.FriendlyName}")
        return None

    except Exception as e:
        return f"Failed to set audio device: {e}"


def _get_master_volume_interface():
    """Helper to get the master volume control interface."""
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume)), None
    except Exception as e:
        return None, f"Could not get audio device interface: {e}"


def volume_up(payload):
    """Increases master volume by a given step."""
    volume, err = _get_master_volume_interface()
    if err:
        return ValueError(err)
    try:
        # Default to a 2% volume step if no payload is provided
        step = float(payload or 0.02)
    except (ValueError, TypeError):
        step = 0.02

    current_volume = volume.GetMasterVolumeLevelScalar()
    new_volume = min(1.0, current_volume + step)
    volume.SetMasterVolumeLevelScalar(new_volume, None)
    return None


def volume_down(payload):
    """Decreases master volume by a given step."""
    volume, err = _get_master_volume_interface()
    if err:
        return ValueError(err)
    try:
        # Default to a 2% volume step if no payload is provided
        step = float(payload or 0.02)
    except (ValueError, TypeError):
        step = 0.02

    current_volume = volume.GetMasterVolumeLevelScalar()
    new_volume = max(0.0, current_volume - step)
    volume.SetMasterVolumeLevelScalar(new_volume, None)
    return None


def toggle_mute(payload=None):
    """Toggles the master mute state."""
    volume, err = _get_master_volume_interface()
    if err:
        return ValueError(err)

    is_muted = volume.GetMute()
    volume.SetMute(not is_muted, None)
    return None
