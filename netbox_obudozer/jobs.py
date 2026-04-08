"""
Фоновые задачи (Background Jobs) для плагина netbox_obudozer

Использует встроенный NetBox JobRunner для асинхронной синхронизации VM.
"""
from netbox.jobs import JobRunner

from .sync import sync_vcenter_vms, sync_cluster_to_service

# Привязки кластер → услуга, которые синхронизируются автоматически после vCenter sync
# Формат: (service_id, cluster_id)
AUTO_CLUSTER_SERVICE_BINDINGS = [
    (52, 49),  # Услуга Keysystems ← кластер Keysystems
]


class VCenterSyncJob(JobRunner):
    """
    Фоновая задача синхронизации VM из vCenter в NetBox.

    Выполняется асинхронно через RQ worker.
    Прогресс отслеживается через self.logger в UI NetBox.

    Использование:
        # Из view или другого кода:
        job = VCenterSyncJob.enqueue()

        # Перенаправить пользователя на страницу отслеживания:
        redirect('core:job', pk=job.pk)
    """

    class Meta:
        name = "vCenter VM Synchronization"
        description = "Синхронизация виртуальных машин из vCenter в NetBox"

    def run(self, *args, **kwargs):
        """
        Основная логика выполнения синхронизации.

        Вызывает sync_vcenter_vms() с передачей self.logger
        для отображения прогресса в UI.

        Args:
            *args: Позиционные аргументы (не используются)
            **kwargs: Именованные аргументы (не используются)

        Raises:
            Exception: При критической ошибке синхронизации
        """
        self.logger.info("🚀 Запуск синхронизации vCenter...")

        try:
            # Вызываем основную функцию синхронизации с logger
            result = sync_vcenter_vms(logger=self.logger)

            # Итоговая статистика
            self.logger.info("=" * 60)
            self.logger.info("✅ Синхронизация завершена успешно")
            self.logger.info(f"Создано VM: {result.created}")
            self.logger.info(f"Обновлено VM: {result.updated}")
            self.logger.info(f"Без изменений: {result.unchanged}")
            self.logger.info(f"Помечено недоступными: {result.marked_missing}")
            self.logger.info(f"Длительность: {result.duration:.2f} сек")
            self.logger.info("=" * 60)

            # Если были ошибки, логируем их
            if result.errors:
                self.logger.warning(f"⚠️ Обнаружено ошибок: {len(result.errors)}")

                # Показываем первые 10 ошибок
                for error in result.errors[:10]:
                    self.logger.error(error)

                # Если ошибок больше 10, уведомляем об этом
                if len(result.errors) > 10:
                    self.logger.warning(f"... и еще {len(result.errors) - 10} ошибок")

            # Автоматическая синхронизация кластеров → услуги
            if AUTO_CLUSTER_SERVICE_BINDINGS:
                self.logger.info("")
                self.logger.info("🔗 Синхронизация кластеров → услуги")
                for service_id, cluster_id in AUTO_CLUSTER_SERVICE_BINDINGS:
                    sync_cluster_to_service(service_id, cluster_id, logger=self.logger)

        except Exception as e:
            # Критическая ошибка - логируем и пробрасываем исключение
            self.logger.error(f"❌ Критическая ошибка синхронизации: {str(e)}")
            raise
