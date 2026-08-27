"""
Фоновые задачи (Background Jobs) для плагина netbox_obudozer

Использует встроенный NetBox JobRunner для асинхронной синхронизации VM.
"""
from netbox.jobs import JobRunner

from .sync import sync_all_vcenters, sync_cluster_to_service

# Привязки кластер → услуга, которые синхронизируются автоматически после vCenter sync
# Формат: (service_id, cluster_id)
AUTO_CLUSTER_SERVICE_BINDINGS = [
    (52, 49),  # Услуга Keysystems ← кластер Keysystems
]


class VCenterSyncJob(JobRunner):
    """
    Фоновая задача синхронизации VM из всех настроенных vCenter в NetBox.

    Проходит по всему списку PLUGINS_CONFIG['vcenters'] последовательно.
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

        Вызывает sync_all_vcenters() с передачей self.logger
        для отображения прогресса в UI.

        Args:
            *args: Позиционные аргументы (не используются)
            **kwargs: Именованные аргументы (не используются)

        Raises:
            Exception: При критической ошибке синхронизации
        """
        self.logger.info("🚀 Запуск синхронизации vCenter...")

        try:
            # Синхронизируем все vCenter из конфигурации
            results = sync_all_vcenters(logger=self.logger)

            # Сводка по каждому vCenter отдельно.
            # Формулировки здесь намеренно отличаются от итогового блока ниже:
            # UI парсит статистику из логов по строкам вида "Создано VM: N".
            if len(results) > 1:
                self.logger.info("")
                self.logger.info("📊 Итоги по vCenter:")
                for result in results:
                    self.logger.info(
                        f"  «{result.vcenter_name}» — "
                        f"создано: {result.created}, "
                        f"обновлено: {result.updated}, "
                        f"без изменений: {result.unchanged}, "
                        f"недоступных: {result.marked_missing}, "
                        f"ошибок: {len(result.errors)}"
                    )

            # Итоговая статистика по всем vCenter
            created = sum(r.created for r in results)
            updated = sum(r.updated for r in results)
            unchanged = sum(r.unchanged for r in results)
            marked_missing = sum(r.marked_missing for r in results)
            duration = sum(r.duration for r in results)
            errors = [
                f"[{r.vcenter_name}] {error}"
                for r in results
                for error in r.errors
            ]

            self.logger.info("=" * 60)
            if errors:
                self.logger.info(f"⚠️ Синхронизация завершена с ошибками ({len(results)} vCenter)")
            else:
                self.logger.info(f"✅ Синхронизация завершена успешно ({len(results)} vCenter)")
            self.logger.info(f"Создано VM: {created}")
            self.logger.info(f"Обновлено VM: {updated}")
            self.logger.info(f"Без изменений: {unchanged}")
            self.logger.info(f"Помечено недоступными: {marked_missing}")
            self.logger.info(f"Длительность: {duration:.2f} сек")
            self.logger.info("=" * 60)

            # Если были ошибки, логируем их
            if errors:
                self.logger.warning(f"⚠️ Обнаружено ошибок: {len(errors)}")

                # Показываем первые 10 ошибок
                for error in errors[:10]:
                    self.logger.error(error)

                # Если ошибок больше 10, уведомляем об этом
                if len(errors) > 10:
                    self.logger.warning(f"... и еще {len(errors) - 10} ошибок")

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
