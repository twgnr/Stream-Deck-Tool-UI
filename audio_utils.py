#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from __future__ import print_function
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import (
    cast, POINTER, c_long, c_int, c_uint, c_ushort, c_ubyte, c_wchar_p, 
    c_void_p
)

#--------------------------------------------------------------------
# Class
#--------------------------------------------------------------------
class IPolicyConfig(c_void_p):
    _iid_ = '{F8679F50-850A-41CF-9C72-430F290290C8}'
    _methods_ = [
        (c_long, 'GetMixFormat', (c_wchar_p, c_void_p)),
        (c_long, 'GetDeviceFormat', (c_wchar_p, c_int, c_void_p)),
        (c_long, 'ResetDeviceFormat', (c_wchar_p,)),
        (c_long, 'SetDeviceFormat', (c_wchar_p, c_void_p, c_void_p)),
        (c_long, 'GetProcessingPeriod', (c_wchar_p, c_int, c_void_p, c_void_p)),
        (c_long, 'SetProcessingPeriod', (c_wchar_p, c_void_p)),
        (c_long, 'GetShareMode', (c_wchar_p, c_void_p)),
        (c_long, 'SetShareMode', (c_wchar_p, c_void_p)),
        (c_long, 'GetPropertyValue', (c_wchar_p, c_void_p, c_void_p)),
        (c_long, 'SetPropertyValue', (c_wchar_p, c_void_p, c_void_p)),
        (c_long, 'SetDefaultEndpoint', (c_wchar_p, c_uint)), # This is the one we need
        (c_long, 'SetEndpointVisibility', (c_wchar_p, c_int)),
    ]


def list_audio_devices():
    """Lists all active audio playback devices."""
    devices = AudioUtilities.GetSpeakers()
    return [device.FriendlyName for device in devices]


def set_default_audio_device(device_name):
    """
    Sets the default audio playback device.
    Args:
        device_name (str): A unique part of the desired device's name.
    
    Returns:
        str: An error message if something fails, otherwise None.
    """
    try:
        devices = AudioUtilities.GetSpeakers()
        target_device = None
        for device in devices:
            if device_name.lower() in device.FriendlyName.lower():
                target_device = device
                break
        
        if not target_device:
            return f"Audio device like '{device_name}' not found."

        # Use comtypes to get the PolicyConfig interface
        policy_config = cast(c_void_p(), POINTER(IPolicyConfig))
        
        # Role 0: eConsole (Games, System Notifications)
        # Role 1: eMultimedia (Music, Videos, etc.)
        # Role 2: eCommunications (Voice chat)
        
        # Set the default device for all roles
        policy_config.SetDefaultEndpoint(target_device.id, 1) # Multimedia
        policy_config.SetDefaultEndpoint(target_device.id, 0) # Console
        policy_config.SetDefaultEndpoint(target_device.id, 2) # Communications
        
        print(f"Set default audio device to: {target_device.FriendlyName}")
        return None # Success
        
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
