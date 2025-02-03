#!/usr/bin/env python
#  Copyright (c) 2021-2024, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
#  Creative Commons BY-NC-SA 4.0 International Public License
#  (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
"""
The NarodMon Cloud Integration Component.

For more details about this sensor, please refer to the documentation at
https://github.com/Limych/ha-narodmon/
"""

import logging
import re
import time
from typing import Any, Final

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_DEVICE_ID,
    ATTR_ICON,
    ATTR_ID,
    ATTR_LATITUDE,
    ATTR_LOCATION,
    ATTR_LONGITUDE,
    ATTR_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DEVICES,
    CONF_NAME,
    CONF_SENSORS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    YAML_DOMAIN,
    NarodmonDataUpdateCoordinator,
)
from .const import (
    ATTR_DEVICE_NAME,
    ATTR_DISTANCE,
    ATTR_LAT,
    ATTR_LON,
    ATTR_SENSOR_ID,
    ATTR_SENSOR_NAME,
    ATTRIBUTION,
    CONF_SENSOR_DISPLAY_NAME,
    CONF_SENSOR_ID_REGEXP,
    CONF_SENSOR_TYPE,
    DOMAIN,
    FRESHNESS_TIME,
    NAME,
    SENSOR_TYPES,
    VERSION,
)

_LOGGER: Final = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up sensor platform."""
    if entry.source == SOURCE_IMPORT:
        config = hass.data[YAML_DOMAIN]
        for index, device_config in enumerate(config.get(CONF_DEVICES)):
            vdev_id = "-".join([entry.entry_id, str(index)])
            coordinator = hass.data[DOMAIN][entry.entry_id][index]
            name = device_config.get(CONF_NAME, hass.config.location_name)
            types = device_config.get(
                CONF_SENSORS, [{CONF_SENSOR_TYPE: t} for t in SENSOR_TYPES]
            )

            sensors = []
            for stype in types:
                if CONF_SENSOR_DISPLAY_NAME in stype:
                    entity_name = " ".join([name, stype[CONF_SENSOR_DISPLAY_NAME]])
                else:
                    entity_name = " ".join(
                        [name, SENSOR_TYPES[stype[CONF_SENSOR_TYPE]][ATTR_NAME]]
                    )
                sensors.append(
                    NarodmonSensor(
                        coordinator,
                        stype,
                        vdev_id,
                        entity_name,
                    )
                )
            if sensors:
                async_add_devices(sensors)


# pylint: disable=too-many-instance-attributes
class NarodmonSensor(CoordinatorEntity, SensorEntity):
    """Implementation of an NarodMon sensor."""

    def __init__(
        self,
        coordinator: NarodmonDataUpdateCoordinator,
        sensor_conf: dict,
        vdev_id: str,
        name: str,
    ) -> None:
        """Class initialization."""
        super().__init__(coordinator)

        sensor_type = sensor_conf[CONF_SENSOR_TYPE]
        self._sensor_conf = sensor_conf
        self._sensor_type_id = SENSOR_TYPES[sensor_type].get(ATTR_ID)
        self._sensor_id = None

        id_regexp = sensor_conf.get(CONF_SENSOR_ID_REGEXP, "*")
        self._attr_unique_id = f"{vdev_id}-{sensor_type}-{id_regexp}"
        self._attr_name = name
        self._attr_icon = SENSOR_TYPES[sensor_type].get(ATTR_ICON)
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type].get(
            ATTR_UNIT_OF_MEASUREMENT
        )
        self._attr_device_class = SENSOR_TYPES[sensor_type].get(ATTR_DEVICE_CLASS)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vdev_id)},
            "name": NAME,
            "model": VERSION,
        }

    def _match(self, narodmon_sensor: dict[str, Any]) -> bool:
        """Check if sensor from Narodmon matches this sensor."""
        return narodmon_sensor["type"] == self._sensor_type_id and (
            CONF_SENSOR_ID_REGEXP not in self._sensor_conf
            or re.match(
                self._sensor_conf[CONF_SENSOR_ID_REGEXP],
                str(narodmon_sensor["id"]),
            )
            is not None
        )

    def _update_state(self) -> None:
        """Update entity state."""
        fresh = int(time.time() - FRESHNESS_TIME)
        show_on_map = self.coordinator.show_on_map
        for sensor in self.coordinator.data:
            if sensor["type"] == self._sensor_type_id and sensor["time"] >= fresh:
                x = self._match(sensor)
                if not x:
                    _LOGGER.debug(
                        "Skip sensor '%d', type '%s' - doesn't match regexp '%s'",
                        sensor["id"],
                        sensor["type"],
                        self._sensor_conf[CONF_SENSOR_ID_REGEXP],
                    )
                    continue

                if self._attr_native_value == sensor["value"]:
                    return

                device = sensor["device"]

                self._attr_native_value = sensor["value"]

                if self._sensor_id != int(sensor["id"]):
                    self._sensor_id = int(sensor["id"])
                    self._attr_extra_state_attributes = {
                        ATTR_ATTRIBUTION: ATTRIBUTION,
                    }

                self._attr_extra_state_attributes[ATTR_SENSOR_ID] = "S" + str(
                    self._sensor_id
                )
                self._attr_extra_state_attributes[ATTR_SENSOR_NAME] = sensor["name"]
                self._attr_extra_state_attributes[ATTR_DEVICE_ID] = "D" + str(
                    device["id"]
                )
                self._attr_extra_state_attributes[ATTR_DEVICE_NAME] = device["name"]
                self._attr_extra_state_attributes[ATTR_DISTANCE] = device["distance"]
                if "location" in device:
                    self._attr_extra_state_attributes[ATTR_LOCATION] = device[
                        "location"
                    ]
                if "lat" in device and "lon" in device:
                    if show_on_map:
                        self._attr_extra_state_attributes[ATTR_LATITUDE] = device["lat"]
                        self._attr_extra_state_attributes[ATTR_LONGITUDE] = device[
                            "lon"
                        ]
                    else:
                        self._attr_extra_state_attributes[ATTR_LAT] = device["lat"]
                        self._attr_extra_state_attributes[ATTR_LON] = device["lon"]

                _LOGGER.debug(
                    "Set sensor '%s' state to %d(%s %s)",
                    self._attr_name,
                    sensor["id"],
                    self._attr_native_value,
                    self._attr_native_unit_of_measurement,
                )
                return

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        self._update_state()
        return super().native_value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        fresh = int(time.time() - FRESHNESS_TIME)
        for sensor in self.coordinator.data:
            if (
                sensor["type"] == self._sensor_type_id
                and sensor["time"] >= fresh
                and (
                    CONF_SENSOR_ID_REGEXP not in self._sensor_conf
                    or re.match(
                        self._sensor_conf[CONF_SENSOR_ID_REGEXP], str(sensor["id"])
                    )
                    is not None
                )
            ):
                return True

        return False
