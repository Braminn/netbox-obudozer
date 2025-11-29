"""
NetBox Custom Scripts для плагина netbox_obudozer

Содержит скрипты для выполнения операций синхронизации через веб-интерфейс NetBox.
Скрипты доступны в разделе "Customization" -> "Scripts".
"""
from extras.scripts import Script
from django.utils.html import format_html

from .sync import sync_vcenter_vms, get_sync_status
from .vmware import get_cluster_group_name
from virtualization.models import VirtualMachine, Cluster, ClusterGroup


class VCenterSyncScript(Script):
    """
    Скрипт синхронизации виртуальных машин из VMware vCenter.
    
    Выполняет синхронизацию данных о VM между vCenter и NetBox:
    - Создает новые VM
    - Обновляет измененные VM
    - Помечает отсутствующие VM
    
    Процесс выполняется в фоне и отображает прогресс в реальном времени.
    """
    
    class Meta:
        name = "vCenter VM Synchronization"
        description = "Синхронизирует виртуальные машины из VMware vCenter с NetBox"
        commit_default = True
        scheduling_enabled = True
    
    def run(self, data, commit):
        """
        Основной метод выполнения скрипта.
        
        Args:
            data: Данные формы (не используются в текущей версии)
            commit: Флаг применения изменений (True - применить, False - dry-run)
        """
        
        # Этап 1: Начало синхронизации (0%)
        self.log_info("=" * 70)
        self.log_info("🚀 Начало синхронизации vCenter → NetBox")
        self.log_info("=" * 70)
        
        # Показываем текущий статус
        status = get_sync_status()
        self.log_info(f"📊 Текущее состояние:")
        self.log_info(f"   • Всего VM в NetBox: {status['total_vms']}")
        self.log_info(f"   • Активных: {status['active_vms']}")
        self.log_info(f"   • Отсутствующих: {status['failed_vms']}")
        self.log_info(f"   • Кластеров: {status['cluster_count']}")
        
        if status['last_sync']:
            self.log_info(f"   • Последняя синхронизация: {status['last_sync']}")
        
        # Этап 2: Проверка подключения (10%)
        self.log_info("")
        self.log_info("⏳ Этап 1/5: Проверка подключения к vCenter...")
        
        if not status['vcenter_available']:
            self.log_failure("❌ vCenter недоступен. Синхронизация невозможна.")
            return
        
        self.log_success("✓ Подключение к vCenter установлено")
        
        # Этап 3: Получение данных (30%)
        self.log_info("")
        self.log_info("⏳ Этап 2/5: Получение списка VM из vCenter...")
        
        if not commit:
            self.log_warning("⚠️  Режим DRY-RUN: изменения не будут сохранены")
        
        # Выполняем синхронизацию
        try:
            result = sync_vcenter_vms()
        except Exception as e:
            self.log_failure(f"❌ Критическая ошибка синхронизации: {str(e)}")
            return
        
        self.log_success(f"✓ Получено VM из vCenter")
        
        # Этап 4: Анализ изменений (50%)
        self.log_info("")
        self.log_info("⏳ Этап 3/5: Анализ изменений...")
        self.log_info(f"   • Новых VM: {result.created}")
        self.log_info(f"   • Обновлений: {result.updated}")
        self.log_info(f"   • Без изменений: {result.unchanged}")
        self.log_info(f"   • Отсутствующих: {result.marked_missing}")
        
        # Этап 5: Применение изменений (70%)
        self.log_info("")
        self.log_info("⏳ Этап 4/5: Применение изменений...")
        
        # Отображаем созданные VM
        if result.created > 0:
            self.log_info("")
            self.log_info(f"➕ Создано {result.created} новых VM:")
            # Получаем последние созданные VM из ClusterGroup
            cluster_group_name = get_cluster_group_name()
            cluster_group = ClusterGroup.objects.get(name=cluster_group_name)
            new_vms = VirtualMachine.objects.filter(
                cluster__group=cluster_group
            ).order_by('-created')[:result.created]
            for vm in new_vms:
                state_icon = "▶️" if vm.status == 'active' else "⏹️"
                self.log_success(f"   {state_icon} {vm.name} ({vm.get_status_display()})")
        
        # Отображаем обновленные VM
        if result.updated > 0:
            self.log_info("")
            self.log_info(f"✏️  Обновлено {result.updated} VM:")
            # Получаем последние обновленные VM
            updated_vms = VirtualMachine.objects.filter(
                cluster__group=cluster_group
            ).order_by('-last_updated')[:result.updated]
            for vm in updated_vms:
                state_icon = "▶️" if vm.status == 'active' else "⏹️"
                self.log_warning(f"   {state_icon} {vm.name} ({vm.get_status_display()})")

        # Отображаем отсутствующие VM
        if result.marked_missing > 0:
            self.log_info("")
            self.log_info(f"🚫 Помечено {result.marked_missing} отсутствующих VM:")
            missing_vms = VirtualMachine.objects.filter(
                cluster__group=cluster_group,
                status='failed'
            )[:result.marked_missing]
            for vm in missing_vms:
                self.log_info(f"   ⚠️  {vm.name} (не найдена в vCenter)")
        
        # Этап 6: Проверка ошибок (90%)
        if result.errors:
            self.log_info("")
            self.log_warning(f"⚠️  Обнаружено {len(result.errors)} ошибок:")
            for error in result.errors:
                self.log_failure(f"   ✗ {error}")
        
        # Этап 7: Завершение (100%)
        self.log_info("")
        self.log_info("=" * 70)
        duration_seconds = float(result.duration) if result.duration else 0.0
        # Форматируем число заранее для безопасности
        duration_formatted = f"{duration_seconds:.2f}"
        self.log_success(f"✅ Синхронизация завершена за {duration_formatted} сек")
        self.log_info("=" * 70)
        
        # Итоговая статистика
        self.log_info("")
        self.log_info("📈 Итоговая статистика:")
        self.log_info(f"   • Создано новых VM: {result.created}")
        self.log_info(f"   • Обновлено VM: {result.updated}")
        self.log_info(f"   • Без изменений: {result.unchanged}")
        self.log_info(f"   • Помечено отсутствующими: {result.marked_missing}")
        self.log_info(f"   • Всего обработано: {result.total_processed}")
        self.log_info(f"   • Ошибок: {len(result.errors)}")
        
        # Финальный статус
        final_status = get_sync_status()
        self.log_info("")
        self.log_info("📊 Финальное состояние:")
        self.log_info(f"   • Всего VM в NetBox: {final_status['total_vms']}")
        self.log_info(f"   • Активных: {final_status['active_vms']}")
        self.log_info(f"   • Отсутствующих: {final_status['failed_vms']}")
        self.log_info(f"   • Кластеров: {final_status['cluster_count']}")
        
        self.log_info("")
        self.log_success("🎉 Готово!")


# Регистрируем скрипт
script_order = (
    VCenterSyncScript,
)
