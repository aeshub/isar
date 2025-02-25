import time
from datetime import datetime
from threading import Thread
from typing import List, Tuple

import pytest
from alitra import Frame, Orientation, Pose, Position
from injector import Injector

from isar.models.communication.queues.queues import Queues
from isar.storage.storage_interface import StorageInterface
from isar.storage.uploader import Uploader
from robot_interface.models.inspection.inspection import ImageMetadata, Inspection
from robot_interface.models.mission.mission import Mission
from robot_interface.telemetry.mqtt_client import MqttClientInterface

MISSION_ID = "some-mission-id"
ARBITRARY_IMAGE_METADATA = ImageMetadata(
    start_time=datetime.now(),
    pose=Pose(
        Position(0, 0, 0, Frame("asset")),
        Orientation(x=0, y=0, z=0, w=1, frame=Frame("asset")),
        Frame("asset"),
    ),
    file_type="jpg",
)
DATA_BYTES: bytes = b"Lets say this is some image data"


class UploaderThread(object):
    def __init__(self, injector) -> None:
        self.injector: Injector = injector
        self.uploader: Uploader = Uploader(
            queues=self.injector.get(Queues),
            storage_handlers=injector.get(List[StorageInterface]),
            mqtt_publisher=injector.get(MqttClientInterface),
        )
        self._thread: Thread = Thread(target=self.uploader.run)
        self._thread.daemon = True
        self._thread.start()


@pytest.fixture
def uploader_thread(injector) -> UploaderThread:
    return UploaderThread(injector=injector)


def test_should_upload_from_queue(uploader_thread) -> None:
    mission: Mission = Mission([])
    inspection: Inspection = Inspection(metadata=ARBITRARY_IMAGE_METADATA)

    message: Tuple[Inspection, Mission] = (
        inspection,
        mission,
    )

    uploader_thread.uploader.upload_queue.put(message)
    time.sleep(1)
    assert uploader_thread.uploader.storage_handlers[0].blob_exists(inspection)


def test_should_retry_failed_upload_from_queue(uploader_thread, mocker) -> None:
    mission: Mission = Mission([])
    inspection: Inspection = Inspection(metadata=ARBITRARY_IMAGE_METADATA)

    message: Tuple[Inspection, Mission] = (
        inspection,
        mission,
    )

    # Need it to fail so that it retries
    uploader_thread.uploader.storage_handlers[0].will_fail = True
    uploader_thread.uploader.upload_queue.put(message)
    time.sleep(1)

    # Should not upload, instead raise StorageException
    assert not uploader_thread.uploader.storage_handlers[0].blob_exists(inspection)
    uploader_thread.uploader.storage_handlers[0].will_fail = False
    time.sleep(3)

    # After 3 seconds, it should have retried and now it should be successful
    assert uploader_thread.uploader.storage_handlers[0].blob_exists(inspection)
