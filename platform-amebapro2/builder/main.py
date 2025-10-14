import os
from SCons.Script import DefaultEnvironment, AlwaysBuild, Alias
import glob
import subprocess
import re
import struct
import shutil

MBEDTLS_VERSION = "2.28.1"
LWIP_VERSION = "v2.1.2"

env = DefaultEnvironment() # SDK 與 Toolchain 路徑

sdk_dir = os.path.join(env.subst("$PROJECT_DIR"), ".pio", "framework-ameba-rtos-pro2")

if not os.path.exists(sdk_dir):
    print(">>> Cloning Ameba Pro2 SDK ...")
    subprocess.check_call([
        "git", "clone", "--depth=1",
        "https://github.com/Ameba-AIoT/ameba-rtos-pro2.git",
        sdk_dir
    ])

sdk_lwipopts = os.path.join(sdk_dir, "component", "lwip", "api", "lwipopts.h")

if os.path.exists(sdk_lwipopts):
    print(f">>> Removing default lwipopts.h: {sdk_lwipopts}")
    os.remove(sdk_lwipopts)

# 讀取開關：platformio.ini 可設 build_flags = -DTRUSTZONE=1
USE_TZ = int(env.GetProjectOption("trustzone") or
             os.environ.get("CONFIG_TRUSTZONE", "0") or
             ("TRUSTZONE" in (env.get("CPPDEFINES") or []) and "1") or
             0)
USE_WLANMP = int(env.GetProjectOption("wlanmp") or
             os.environ.get("CONFIG_USE_WLANMP", "0") or
             ("USE_WLANMP" in (env.get("CPPDEFINES") or []) and "1") or
             0)
MPCHIP     = int(env.GetProjectOption("mpchip") or
             os.environ.get("CONFIG_MPCHIP", "0") or
             ("MPCHIP" in (env.get("CPPDEFINES") or []) and "1") or
             0)
UNITEST    = int(env.GetProjectOption("unitest") or
             os.environ.get("CONFIG_UNITEST", "0") or
             ("UNITEST" in (env.get("CPPDEFINES") or []) and "1") or
             0)

# 兼容多種格式
flags = env.GetProjectOption("build_flags")
if not flags:
    flags = []
elif isinstance(flags, str):
    flags = [flags]

include_dirs = []
for f in flags:
    f = f.strip()
    if f.startswith("-I"):
        # 移除 -I，轉成絕對路徑
        path = f[2:]
        if not os.path.isabs(path):
            path = os.path.join(env.subst("$PROJECT_DIR"), path)
        include_dirs.append(path)

project_application_dir   = os.path.join(env.subst("$PROJECT_DIR"), "src")
project_include_dir       = os.path.join(env.subst("$PROJECT_DIR"), "include")
project_models_dir        = os.path.join(env.subst("$PROJECT_DIR"), "models/model_nb")
sdk_project_root_dir      = os.path.join(sdk_dir, "project", "realtek_amebapro2_v0_example/GCC-RELEASE")
sdk_cmake_ROM_dir         = os.path.join(sdk_project_root_dir, "ROM/GCC")
sdk_cmake_bootloader_dir  = os.path.join(sdk_project_root_dir, "bootloader")
sdk_cmake_application_dir = os.path.join(sdk_project_root_dir, "application")
sdk_mp_dir                = os.path.join(sdk_project_root_dir, "mp")

# 複製 json（跟 CMake 同一路徑）
sdk_key_cfg_path                       = os.path.join(sdk_mp_dir, "key_cfg.json")
sdk_certificate_json                   = os.path.join(sdk_mp_dir, "certificate.json")
sdk_amebapro2_partitiontable_path      = os.path.join(sdk_mp_dir, "amebapro2_partitiontable.json")
sdk_amebapro2_bootloader_path          = os.path.join(sdk_mp_dir, "amebapro2_bootloader.json")
sdk_amebapro2_nn_model_path            = os.path.join(sdk_mp_dir, "amebapro2_nn_model.json")
sdk_amebapro2_fwfs_nn_models_path      = os.path.join(sdk_mp_dir, "amebapro2_fwfs_nn_models.json")
sdk_amebapro2_isp_iq_json              = os.path.join(sdk_mp_dir, "amebapro2_isp_iq.json")
sdk_amebapro2_sensor_set_json          = os.path.join(sdk_mp_dir, "amebapro2_sensor_set.json")

sdk_voe_bin_dir = os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/source/ram/video/voe_bin")

if USE_TZ:
    sdk_amebapro2_application_path     = os.path.join(sdk_mp_dir, "amebapro2_firmware_tz.json")
else:
    sdk_amebapro2_application_path     = os.path.join(sdk_mp_dir, "amebapro2_firmware_ntz.json")

if os.name=="nt":
    sdk_nn_model_cfg_path              = os.path.join(sdk_mp_dir, "nn_model_cfg.exe")
    sdk_elf2bin_path                   = os.path.join(sdk_mp_dir, "elf2bin.exe")
    sdk_checksum_path                  = os.path.join(sdk_mp_dir, "checksum.exe")
    sdk_gensnrlst_path                 = os.path.join(sdk_mp_dir, "gen_snrlst.exe")
else:
    sdk_nn_model_cfg_path              = os.path.join(sdk_mp_dir, "nn_model_cfg.linux")
    sdk_elf2bin_path                   = os.path.join(sdk_mp_dir, "elf2bin.linux")
    sdk_checksum_path                  = os.path.join(sdk_mp_dir, "checksum.linux")
    sdk_gensnrlst_path                 = os.path.join(sdk_mp_dir, "gen_snrlst.linux")

toolchain = env.PioPlatform().get_package_dir("toolchain-gccarmnoneeabi")

gcc = os.path.join(toolchain, "bin", "arm-none-eabi-gcc")
ld = os.path.join(toolchain, "bin", "arm-none-eabi-ld")
objcopy = os.path.join(toolchain, "bin", "arm-none-eabi-objcopy")
strip = os.path.join(toolchain, "bin", "arm-none-eabi-strip")
objdump = os.path.join(toolchain, "bin", "arm-none-eabi-objdump")
nm = os.path.join(toolchain, "bin", "arm-none-eabi-nm")

# build 目錄 
build_dir = os.path.join(env.subst("$BUILD_DIR"), "amebapro2")
if not os.path.exists(build_dir): 
    os.makedirs(build_dir) 

def _safe_copy(src, dst):
    import shutil, os
    if os.path.exists(src):
        shutil.copy2(src, dst)
        return True
    print(f">>> WARN: {src} not found; skip copy")
    return False

# bootloader sources/inc 
bootloader_src = [
    os.path.join(sdk_dir, "component/video/driver/RTL8735B/video_user_boot.c"),
    os.path.join(sdk_dir, "component/video/driver/RTL8735B/video_boot.c"),
    os.path.join(sdk_dir, "component/soc/8735b/misc/platform/user_boot.c"),
]
bootloader_inc = [
    os.path.join(sdk_dir, "component/stdlib"),

    os.path.join(sdk_dir, "component/soc/8735b/cmsis/cmsis-core/include"),
    os.path.join(sdk_dir, "component/soc/8735b/cmsis/rtl8735b/include"),
    os.path.join(sdk_dir, "component/soc/8735b/cmsis/rtl8735b/lib/include"),

    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/include"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/include"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/source/ram/video"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/source/ram/video/enc/inc"),

    os.path.join(sdk_dir, "component/soc/8735b/app/rtl_printf/include"),
    os.path.join(sdk_dir, "component/soc/8735b/app/stdio_port"),

    os.path.join(sdk_dir, "component/soc/8735b/misc/utilities/include"),

    os.path.join(sdk_dir, "component/soc/8735b/mbed-drivers/include"),

    os.path.join(sdk_dir, "component/os/os_dep/include"),

    os.path.join(sdk_dir, "component/os/freertos"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/include"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/GCC/ARM_CM23/non_secure"),
]

# application sources/inc 
application_src = [ 
    os.path.join(sdk_dir, "component/soc/8735b/app/shell/cmd_shell.c"),
    
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_adc.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_audio.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_clk.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_comp.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_crypto.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_dram_init.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_dram_scan.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_ecdsa.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_eddsa.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_eth.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_flash.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_gdma.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_gpio.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_i2c.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_i2s.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_pwm.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_rsa.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_sdhost.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_sgpio.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_snand.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_spic.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_sport.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_ssi.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_timer.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_trng.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/hal_uart.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_audio.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_eth.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_i2s.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_sgpio.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_sport.c"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram/rtl8735b_ssi.c"),

    os.path.join(sdk_dir, "component/soc/8735b/mbed-drivers/source/us_ticker_api.c"),
    os.path.join(sdk_dir, "component/soc/8735b/mbed-drivers/source/wait_api.c"),
    
    os.path.join(sdk_dir, "component/soc/8735b/misc/driver/flash_api_ext.c"),

    os.path.join(sdk_dir, "component/wifi/api/wifi_conf_ext.c"),
    os.path.join(sdk_dir, "component/wifi/api/wifi_conf_inter.c"),
    #os.path.join(sdk_dir, "component/wifi/api/wifi_conf_wowlan.c"),
    os.path.join(sdk_dir, "component/wifi/api/wifi_conf.c"),
    os.path.join(sdk_dir, "component/wifi/api/wifi_ind.c"),
    os.path.join(sdk_dir, "component/wifi/api/wlan_network.c"),

    os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_crypto_ssl.c"),
    os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_power_by_rate.c"),
    os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_power_limit.c"),
    os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_rf_para_rtl8735b.c"),
    os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_skbuf_rtl8735b.c"),
    #os.path.join(sdk_dir, "component/wifi/driver/src/core/option/rtw_opt_skbuf.c"),

    os.path.join(sdk_dir, "component/wifi/driver/src/osdep/lwip_intf.c"),

    os.path.join(sdk_dir, "component/wifi/promisc/wifi_conf_promisc.c"),
    os.path.join(sdk_dir, "component/wifi/promisc/wifi_promisc.c"),

    os.path.join(sdk_dir, "component/wifi/wifi_config/wifi_simple_config.c"),

    os.path.join(sdk_dir, "component/wifi/wifi_fast_connect/wifi_fast_connect.c"),

    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/hci/bt_fwconfig.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/hci/bt_mp_patch.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/hci/bt_normal_patch.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/hci/hci_board.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/hci/hci_uart.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/platform_utils.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/rtk_coex.c"),
    #os.path.join(sdk_dir, "component/bluetooth/realtek/sdk/board/amebapro2/src/trace_uart.c"),

    os.path.join(sdk_dir, "component/ssl/ssl_func_stubs/ssl_func_stubs.c"),
    #os.path.join(sdk_dir, "component/ssl/ssl_ram_map/ssl_ram_map.c"),
    os.path.join(sdk_dir, "component/ssl/ssl_ram_map/rom/rom_ssl_ram_map.c"),

    os.path.join(sdk_dir, "component/network/dhcp/dhcps.c"),
    
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/analogin_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/audio_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/crypto_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/dma_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/ecdsa_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/efuse_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/ethernet_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/flash_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/gpio_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/gpio_irq_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/i2c_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/i2s_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/pinmap_common.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/pinmap.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/power_mode_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/pwmout_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/rtc_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/serial_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/sgpio_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/snand_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/spi_api.c"),
    #os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/sport_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/sys_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/timer_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/trng_api.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/us_ticker.c"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b/wdt_api.c"),
    
    os.path.join(sdk_dir, f"component/lwip/api/lwip_netconf.c"),

    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos/br_rpt_handle.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos/bridgeif_fdb.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos/bridgeif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos/ethernetif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos/sys_arch.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/api_lib.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/api_msg.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/err.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/if_api.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/netbuf.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/netdb.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/netifapi.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/sockets.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/api/tcpip.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/altcp_alloc.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/altcp_tcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/altcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/def.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/dns.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/inet_chksum.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/init.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ip.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/mem.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/memp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/netif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/pbuf.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/raw.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/stats.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/sys.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/tcp_in.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/tcp_out.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/tcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/timeouts.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/udp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/autoip.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/dhcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/etharp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/icmp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/igmp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/ip4_addr.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/ip4_frag.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv4/ip4.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/dhcp6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/ethip6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/icmp6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/inet6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/ip6_addr.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/ip6_frag.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/ip6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/mld6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/core/ipv6/nd6.c"),
    #os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/bridgeif_fdb.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/bridgeif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ethernet.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/lowpan6_ble.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/lowpan6_common.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/lowpan6.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/slipif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/zepif.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/auth.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/ccp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/chap_ms.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/chap-md5.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/chap-new.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/demand.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/eap.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/ecp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/eui64.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/fsm.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/ipcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/ipv6cp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/lcp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/magic.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/mppe.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/multilink.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/ppp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/pppapi.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/pppcrypt.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/pppoe.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/pppol2tp.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/pppos.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/upap.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/utils.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/vj.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/polarssl/arc4.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/polarssl/des.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/polarssl/md4.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/polarssl/md5.c"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/netif/ppp/polarssl/sha1.c"),
    
    #os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/mbedtls_rom_test.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/aes_alt.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/aes.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/aesni.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/arc4.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/aria.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/asn1parse.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/asn1write.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/base64.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/bignum.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/blowfish.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/camellia.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ccm.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/certs.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/chacha20.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/chachapoly.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/cipher_wrap.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/cipher.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/cmac.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/constant_time.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ctr_drbg.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/debug.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/des.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/dhm.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ecdh.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ecdsa.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ecjpake.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ecp_curves.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ecp.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/entropy_alt.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/entropy_poll.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/entropy.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/error.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/gcm_alt.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/gcm.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/havege.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/hmac_drbg.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/md.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/md2.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/md4.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/md5.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/memory_buffer_alloc.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/mps_reader.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/mps_trace.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/net_sockets.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/nist_kw.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/oid.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/padlock.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pem.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pk_wrap.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pk.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pkcs5.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pkcs11.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pkcs12.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pkparse.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/pkwrite.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/platform_util.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/platform.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/poly1305.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_aead.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_cipher.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_client.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_driver_wrappers.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_ecp.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_hash.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_mac.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_rsa.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_se.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_slot_management.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto_storage.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_crypto.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/psa_its_file.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ripemd160.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/rsa_internal.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/rsa.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/sha1.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/sha256.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/sha512.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_cache.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_ciphersuites.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_cli.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_cookie.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_msg.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_srv.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_ticket.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_tls.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/ssl_tls13_keys.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/threading.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/timing.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/version_features.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/version.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509_create.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509_crl.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509_crt.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509_csr.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509write_crt.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/x509write_csr.c"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/library/xtea.c"),
    
    os.path.join(sdk_dir, "component/os/os_dep/device_lock.c"),
    os.path.join(sdk_dir, "component/os/os_dep/osdep_service.c"),
    os.path.join(sdk_dir, "component/os/os_dep/tcm_heap.c"),

    os.path.join(sdk_dir, "component/os/freertos/cmsis_os.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_cb.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_heap_rtk.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_service.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_wrapper.c"),

    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/list.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/queue.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/tasks.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/timers.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/croutine.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/event_groups.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/stream_buffer.c"),
    #os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/MemMang/heap_5.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/GCC/ARM_CM33/non_secure/port.c"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/GCC/ARM_CM33/non_secure/portasm.c"),
]

if USE_TZ:
    application_src += [
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_eth_nsc.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_flash_sec.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_hkdf.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_pinmux_nsc.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_rtc_nsc.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_rtc.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_trng_sec.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_s/hal_wdt.c"),
    ]
else:
    application_src += [
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_ns/hal_flash_ns.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_ns/hal_spic_ns.c"),
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/source/ram_ns/hal_wlan.c"),
    ]

application_inc = [
    os.path.join(sdk_dir, "component/stdlib"),

    os.path.join(sdk_dir, "component/soc/8735b/cmsis/cmsis-core/include"),
    os.path.join(sdk_dir, "component/soc/8735b/cmsis/rtl8735b/include"),
    os.path.join(sdk_dir, "component/soc/8735b/cmsis/rtl8735b/lib/include"),

    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/include"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/include"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/source/ram/video"),
    os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/source/ram/video/enc/inc"),

    os.path.join(sdk_dir, "component/soc/8735b/app/shell"),
    os.path.join(sdk_dir, "component/soc/8735b/app/rtl_printf/include"),
    os.path.join(sdk_dir, "component/soc/8735b/app/stdio_port"),

    os.path.join(sdk_dir, "component/soc/8735b/misc/utilities/include"),

    os.path.join(sdk_dir, "component/soc/8735b/mbed-drivers/include"),

    os.path.join(sdk_dir, "component/wifi/api"),
    os.path.join(sdk_dir, "component/wifi/driver/include"),
    os.path.join(sdk_dir, "component/wifi/driver/src/osdep"),
    os.path.join(sdk_dir, "component/wifi/wifi_fast_connect"),

    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/board/amebapro2/lib"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/board/amebapro2/src"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/board/amebapro2/src/vendor_cmd"),

    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/board/common/inc"),

    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/inc/os"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/inc/platform"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/inc/stack"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/inc/bluetooth/gap"),
    #os.path.join(sdk_dir, "component/common/bluetooth/realtek/sdk/inc/bluetooth/profile"),
    
    os.path.join(sdk_dir, "component/lwip/api"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/port/realtek/freertos"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/include"),
    os.path.join(sdk_dir, f"component/lwip/lwip_{LWIP_VERSION}/src/include/lwip"),
    os.path.join(sdk_dir, "component/ssl/ssl_func_stubs/rom"),
    os.path.join(sdk_dir, "component/ssl/ssl_ram_map/rom"),
    os.path.join(sdk_dir, f"component/ssl/mbedtls-{MBEDTLS_VERSION}/include"),

    os.path.join(sdk_dir, "component/network"),

    os.path.join(sdk_dir, "component/file_system/system_data"),

    os.path.join(sdk_dir, "component/mbed/api"),
    os.path.join(sdk_dir, "component/mbed/hal"),
    os.path.join(sdk_dir, "component/mbed/hal_ext"),
    os.path.join(sdk_dir, "component/mbed/targets/hal/rtl8735b"),

    os.path.join(sdk_dir, "component/soc/8735b/cmsis/rtl8735b/include"),

    os.path.join(sdk_dir, "component/os/os_dep/include"),
    os.path.join(sdk_dir, "component/os/freertos"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/include"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/GCC/ARM_CM33/non_secure"),
    os.path.join(sdk_dir, "component/os/freertos/freertos_v202210.01/Source/portable/GCC/ARM_CM33/secure"),
] 

# .a libraries
extra_libs_bootloader = []
extra_libs_application = [] 

def norm_unix(path):
    return path.replace("\\", "/")

def collect_sources(root, exts=(".c", ".cpp")):
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(root, "**", "*" + ext), recursive=True))
    return files

def _mk_objs(envx, srcs, suffix, obj_root): 
    objs = [] 
    for s in srcs: 
        rel = os.path.relpath(s, sdk_dir).replace("\\", "/") 
        obj = os.path.join(obj_root, rel) + suffix + ".o"
        os.makedirs(os.path.dirname(obj), exist_ok=True)
        objs.append(envx.Object(target=obj, source=s)) 
    return objs

toolbin = os.path.join(toolchain, "bin")

def set_xtools(e):
    e.Replace( CC=os.path.join(toolbin, "arm-none-eabi-gcc"),
              CXX=os.path.join(toolbin, "arm-none-eabi-g++"),
              AS=os.path.join(toolbin, "arm-none-eabi-gcc"),
              AR=os.path.join(toolbin, "arm-none-eabi-ar"),
              RANLIB=os.path.join(toolbin, "arm-none-eabi-ranlib"),
              OBJCOPY=os.path.join(toolbin, "arm-none-eabi-objcopy"),
              OBJDUMP=os.path.join(toolbin, "arm-none-eabi-objdump"),
              NM=os.path.join(toolbin, "arm-none-eabi-nm"),
              SIZE=os.path.join(toolbin, "arm-none-eabi-size"), ) 
    
    # 保險：把 toolchain/bin 也塞進 PATH（有些外部腳本/工具會用到） 
    e.PrependENVPath("PATH", toolbin) 

def apply_ini_build_flags(envx): 
    raw = envx.GetProjectOption("build_flags") or ""
    flags = envx.ParseFlags(raw)
    envx.AppendUnique( CPPDEFINES = flags.get("CPPDEFINES", []), # -D
                       CCFLAGS = flags.get("CCFLAGS", []),
                       CFLAGS = flags.get("CFLAGS", []),
                       CXXFLAGS = flags.get("CXXFLAGS", []),
                       ASFLAGS = flags.get("ASFLAGS", []),
                       LINKFLAGS = flags.get("LINKFLAGS", []),
                       CPPPATH = flags.get("CPPPATH", []), # -I 
                       LIBPATH = flags.get("LIBPATH", []), # -L 
                       LIBS = flags.get("LIBS", []), # -l
                    ) 
    
proj_include = os.path.join(env.subst("$PROJECT_DIR"), "include")

# Build bootloader
env_bootloader = env.Clone()
set_xtools(env_bootloader)
apply_ini_build_flags(env_bootloader)
env_bootloader.Append(CCFLAGS=[
    "-mcpu=cortex-m23", "-mthumb", "-mcmse",
    "-Os", "-fno-common", "-fmessage-length=0",
    "-Wall", "-Wpointer-arith", "-Wstrict-prototypes",
    "-Wundef", "-Wno-unused-function", "-Wno-unused-variable",
    "-ffunction-sections","-fdata-sections",
    "-Wno-int-conversion",
    "-Wno-implicit-function-declaration",
    "-Wno-incompatible-pointer-types"
])
env_bootloader.Append(CPPPATH=[include_dirs])
env_bootloader.Append(CPPPATH=[proj_include])
env_bootloader.Append(CCFLAGS=[
    "-D__ARM_FEATURE_CMSE=3",
	"-DCONFIG_BUILD_BOOT=1",
	"-DCONFIG_BUILD_RAM=1 ",
	"-DCONFIG_BUILD_LIB=1 ",
	"-DCONFIG_PLATFORM_8735B",
	"-DCONFIG_RTL8735B_PLATFORM=1",
])
env_bootloader.Append(CPPPATH=bootloader_inc, CPPDEFINES=env.get("CPPDEFINES", []))
bootloader_objs = _mk_objs(env_bootloader, bootloader_src, ".bootloader", os.path.join(env.subst("$BUILD_DIR"), "amebapro2/bootloader/obj"))
bootloader_elf = env_bootloader.Program(
    target=os.path.join(env.subst("$BUILD_DIR"), "amebapro2/bootloader.elf"),
    source=bootloader_objs,
    LIBPATH=[os.path.join(sdk_cmake_ROM_dir)],
    LIBS=extra_libs_bootloader,
    LINKFLAGS=[
        "-mcpu=cortex-m23", "-mthumb", "-mcmse",
        "-Wl,--whole-archive",
        os.path.join(sdk_dir, "component/soc/8735b/fwlib/rtl8735b/lib/lib/hal_pmc.a"),
        os.path.join(sdk_cmake_bootloader_dir, "output", "libboot.a"),
        "-Wl,--no-whole-archive",
        "-T" + os.path.join(sdk_cmake_bootloader_dir, "rtl8735b_boot_mp.ld"),
        "-nostartfiles", "--specs=nosys.specs",
        "-Wl,--gc-sections", "-Wl,--warn-section-align",
        "-Wl,-Map=" + os.path.join(build_dir, "target_bootloader.map"),
        "-Wl,--cref", "-Wl,--no-enum-size-warning",
    ]
)

# Build application
env_application = env.Clone()
set_xtools(env_application)
apply_ini_build_flags(env_application)
env_application.Append(CCFLAGS=[
    "-mcpu=cortex-m33", "-mthumb", "-mcmse", "-mfpu=fpv5-sp-d16", "-mfloat-abi=hard",
    "-Os", "-fno-common", "-fmessage-length=0",
    "-Wall", "-Wpointer-arith", "-Wstrict-prototypes",
    "-Wundef", "-Wno-unused-function", "-Wno-unused-variable",
    "-ffunction-sections","-fdata-sections",
    "-Wno-int-conversion",
    "-Wno-implicit-function-declaration",
    "-Wno-incompatible-pointer-types"
])
env_application.Append(CCFLAGS=[
	"-DCONFIG_BUILD_RAM=1 ",
	"-DCONFIG_PLATFORM_8735B",
	"-DCONFIG_RTL8735B_PLATFORM=1",
	"-DCONFIG_SYSTEM_TIME64=1",
])
if USE_TZ:
    env_application.Append(CCFLAGS=[f"-DCONFIG_BUILD_SECURE=1"])
else:
    env_application.Append(CCFLAGS=[f"-DCONFIG_BUILD_NONSECURE=1"])
    env_application.Append(CCFLAGS=[f"-DENABLE_SECCALL_PATCH"])
env_application.Append(CPPPATH=[include_dirs])
env_application.Append(CPPPATH=[proj_include])
env_application.Append(CPPPATH=application_inc, CPPDEFINES=env.get("CPPDEFINES", []))
application_objs = _mk_objs(env_application, application_src, ".application", os.path.join(env.subst("$BUILD_DIR"), "amebapro2/application/obj"))
application_proj_src = collect_sources(project_application_dir)
application_proj_objs = _mk_objs(env_application, application_proj_src, ".application", os.path.join(env.subst("$BUILD_DIR"), "amebapro2/application/obj"))
if USE_TZ:
    application_elf = env_application.Program(
        target=os.path.join(env.subst("$BUILD_DIR"), "amebapro2/application.elf"),
        source=application_objs + application_proj_objs,
        LIBPATH=[os.path.join(sdk_cmake_application_dir, "lib/application")],
        LIBS=extra_libs_application,
        LINKFLAGS=[
            "-mcpu=cortex-m33", "-mthumb", "-mcmse", "-mfpu=fpv5-sp-d16", "-mfloat-abi=hard",
            "-L" + sdk_cmake_ROM_dir,
            "-T" + os.path.join(sdk_cmake_application_dir, "rtl8735b_ram_ns.ld"),
            "-nostartfiles", "--specs=nosys.specs",
            "-Wl,--gc-sections", "-Wl,--warn-section-align",
            "-Wl,-Map=" + os.path.join(build_dir, "target_application.map"),
            "-Wl,--cref", "-Wl,--no-enum-size-warning",
        ]
    )
else:
    application_elf = env_application.Program(
        target=os.path.join(env.subst("$BUILD_DIR"), "amebapro2/application.elf"),
        source=application_objs + application_proj_objs,
        LIBPATH=[os.path.join(sdk_cmake_application_dir, "lib/application")],
        LIBS=extra_libs_application,
        LINKFLAGS=[
            "-mcpu=cortex-m33", "-mthumb", "-mcmse", "-mfpu=fpv5-sp-d16", "-mfloat-abi=hard",
            "-L" + sdk_cmake_ROM_dir,
            "-T" + os.path.join(sdk_cmake_application_dir, "rtl8735b_ram.ld"),
            "-nostartfiles", "--specs=nosys.specs",
            "-Wl,--gc-sections", "-Wl,--warn-section-align",
            "-Wl,-Map=" + os.path.join(build_dir, "target_application.map"),
            "-Wl,--cref", "-Wl,--no-enum-size-warning",
        ]
    )
    
def _run(cmd, strict=True, cwd=None):
    import subprocess, shlex
    # 支援 list 或字串
    if isinstance(cmd, str):
        printable = cmd
        r = subprocess.run(cmd, capture_output=True, text=True, shell=True, cwd=cwd)
    else:
        printable = " ".join(cmd)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    print(">>>", printable)
    if r.stdout: print(r.stdout)
    if r.stderr: print(r.stderr)
    if strict and r.returncode != 0:
        raise RuntimeError(f"Command failed: {printable}")
    return r.returncode

def _pad_to_4k(path: str):
    import os
    sz = os.stat(path).st_size
    newsize = (((sz - 1) >> 12) + 1) << 12 if sz else 0
    pad = newsize - sz
    if pad > 0:
        with open(path, "ab", buffering=0) as f:
            for _ in range(pad):
                f.write(b"\xFF")

def _touch_4k(path):
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(b"\xFF"*4096)

def _concat_bins(out_path:str, *parts:str):
    with open(out_path, "wb") as w:
        for p in parts:
            if not p: 
                continue
            with open(p, "rb") as r:
                w.write(r.read())

def _flash_action(target, source, env):
    tgt = "flash_tz" if USE_TZ else "flash_ntz"
    if USE_WLANMP:
        tgt += "_mp"
    out = os.path.join(build_dir, f"{tgt}.bin")

    # 確保要用到的檔案都在 build_dir
    fw  = os.path.join(build_dir, "firmware.bin")
    app = os.path.join(build_dir, "application.bin")
    if (not os.path.exists(fw)) and os.path.exists(app):
        _safe_copy(app, fw)
    isp = os.path.join(build_dir, "firmware_isp_iq.bin")
    if not os.path.exists(isp):
        _touch_4k(isp)  # 沒有就補一份空的，避免 combine 抱怨

    part_json = sdk_amebapro2_partitiontable_path
    if MPCHIP:
        mapping = "CER_TBL=certable.bin,KEY_CER1=certificate.bin,PT_BL_PRI=boot.bin,PT_FW1=firmware.bin,PT_ISP_IQ=firmware_isp_iq.bin"
        if os.path.exists(os.path.join(build_dir, "boot_fcs.bin")):
            mapping += ",PT_FCSDATA=boot_fcs.bin"
    else:
        mapping = "BOOT=boot.bin,FW1=firmware.bin,PT_ISP_IQ=firmware_isp_iq.bin"

    # 讓 elf2bin 在 build_dir 執行，mapping 的相對檔名就能打得到
    _run([sdk_elf2bin_path, "combine", part_json, out, mapping], cwd=build_dir)

    # 產 OTA（有才做 checksum）
    for src, dst in [("firmware.bin","ota.bin"),
                     ("firmware_isp_iq.bin","isp_iq_ota.bin"),
                     ("boot.bin","boot_ota.bin")]:
        if _safe_copy(os.path.join(build_dir, src), os.path.join(build_dir, dst)):
            try: _run([sdk_checksum_path, os.path.join(build_dir, dst)], strict=False)
            except Exception as e: print(">>> WARN: sdk_checksum_path skipped:", e)

    print(">>> flash done:", out)
    return 0

def postprocess_bootloader_with_elf2bin():
    image_out = build_dir
    os.makedirs(image_out, exist_ok=True)

    boot_elf = os.path.join(build_dir, "bootloader.elf")
    if not os.path.exists(boot_elf):
        raise FileNotFoundError("bootloader.elf not found")

    # 對齊 CMake：產生 map/asm/axf（純給人看）
    with open(os.path.join(image_out, "bootloader.asm"), "w") as wf:
        subprocess.run([objdump, "-d", boot_elf], stdout=wf)
    shutil.copyfile(boot_elf, os.path.join(image_out, "bootloader.axf"))

    if not MPCHIP:
        # keygen + convert（與 CMake 相同參數）
        _run([sdk_elf2bin_path, "keygen", sdk_key_cfg_path, "key"], cwd=image_out)
        _run([sdk_elf2bin_path, "convert", sdk_amebapro2_bootloader_path, "BOOTLOADER", "boot.bin"], cwd=image_out)

    else:
        # MPCHIP：把 POSTBUILD_BOOT 當成 json
        _run([sdk_elf2bin_path, "convert", sdk_amebapro2_bootloader_path, "BOOTLOADER", "boot.bin"], cwd=image_out)

    # boot.bin 應該已經存在
    boot_bin = os.path.join(image_out, "boot.bin")
    if not os.path.exists(boot_bin):
        # 有些 elf2bin 專案檔會直接輸出到 output/，幫你搬回 build_dir
        cand = glob.glob(os.path.join(image_out, "output", "boot.bin"))
        if cand:
            shutil.copy2(cand[0], boot_bin)

    if not os.path.exists(boot_bin):
        print(">>> WARN: boot.bin not found after elf2bin convert（請檢查 json / sdk_elf2bin_path）")

    # 盡力在 build_dir 找出含 video_user_boot 的物件
    bootfcs_obj = os.path.join(build_dir, "bootloader/obj/component/video/driver/RTL8735B/video_user_boot.c.bootloader.o")
    
    if os.path.exists(bootfcs_obj):
        tmpo = os.path.join(image_out, "tmp_bootfcs.o")
        shutil.copyfile(bootfcs_obj, tmpo)
        _run([objcopy, "-O", "binary", tmpo, "boot_fcs.bin", "-j", ".data.video_boot_stream"], strict=False, cwd=image_out)
        if os.path.exists(os.path.join(image_out, "boot_fcs.bin")):
            # chksum（可選）
            try:
                _run([sdk_checksum_path, "-m", "fcs","boot_fcs.bin"], strict=False, cwd=image_out)
            except Exception as e:
                print(">>> WARN: chksum 工具不可用，略過：", e)
        try:
            os.remove(tmpo)
        except OSError:
            pass
    else:
        print(">>> WARN: 找不到 bootfcs 物件，無法抽出 boot_fcs.bin（可透過環境變數 FCS_FB_OBJ 指定 .o 檔路徑）")

    # 對齊 CMake：輸出 output/ 目錄
    outdir = os.path.join(image_out, "output")
    os.makedirs(outdir, exist_ok=True)
    for f in ("boot.bin", "bootloader.axf", "boot_fcs.bin"):
        p = os.path.join(image_out, f)
        if os.path.exists(p):
            _safe_copy(p, os.path.join(outdir, f))

    # 盡力複製 nm.map / asm，名稱與 CMake 接近
    try:
        with open(os.path.join(image_out, "bootloader.nm.map"), "w", encoding="utf-8") as wf:
            subprocess.run([nm, "-n", boot_elf], stdout=wf, text=True, check=False)
        with open(os.path.join(image_out, "bootloader.asm"), "w", encoding="utf-8") as wf:
            subprocess.run([objdump, "-d", boot_elf], stdout=wf, text=True, check=False)
        _safe_copy(os.path.join(image_out, "bootloader.nm.map"), os.path.join(outdir, "bootloader.nm.map"))
        _safe_copy(os.path.join(image_out, "bootloader.asm"),    os.path.join(outdir, "bootloader.asm"))
    except Exception:
        pass

    print(">>> bootloader (sdk_elf2bin_path) done")
    # 回傳可能會被 imagetool 合併用到的路徑（若不存在，也不致於中斷）
    return boot_bin if os.path.exists(boot_bin) else None,

def _sensor_iq_action(target, source, env):
    os.makedirs(build_dir, exist_ok=True)

    # 1) 複製 VOE 的 IQ/FCS 素材到工作目錄
    for p in glob.glob(os.path.join(sdk_voe_bin_dir, "*.bin")):
        _safe_copy(p, os.path.join(build_dir, os.path.basename(p)))

    # 3) 由 sensor.h 產出/更新清單（CMake 的 GENSNRLST）
    if os.path.exists(sdk_gensnrlst_path):
        try:
            _run([sdk_gensnrlst_path, os.path.join(project_include_dir,"sensor.h")], cwd=build_dir, strict=False)
        except Exception as e:
            print(">>> WARN: gen_snrlst failed:", e)
    else:
        print(">>> NOTE: gen_snrlst tool not found:", sdk_gensnrlst_path)

    # 4) 產生 iq_set.bin（= ISP_SENSOR_SETS）
    _run([sdk_elf2bin_path, "convert", sdk_amebapro2_sensor_set_json, "ISP_SENSOR_SETS", "iq_set.bin"], cwd=build_dir)

    # 同步一份傳統檔名（若你的其他腳本在找 isp_iq.bin）
    _safe_copy(os.path.join(build_dir, "iq_set.bin"), os.path.join(build_dir, "isp_iq.bin"))

    # 5) 產生 firmware_isp_iq.bin（打包給分區）
    _run([sdk_elf2bin_path, "convert", sdk_amebapro2_isp_iq_json, "FIRMWARE", "firmware_isp_iq.bin"], cwd=build_dir)

    print(">>> sensor IQ done:", os.path.join(build_dir, "iq_set.bin"),
          " & ", os.path.join(build_dir, "firmware_isp_iq.bin"))
    return 0

def postprocess_application_with_elf2bin():
    image_out = build_dir
    os.makedirs(image_out, exist_ok=True)

    app_elf = os.path.join(build_dir, "application.elf")
    if not os.path.exists(app_elf):
        raise FileNotFoundError("application.elf not found")

    # 可讀性輸出：asm/map/axf（與 bootloader 對齊）
    try:
        with open(os.path.join(image_out, "application.nm.map"), "w", encoding="utf-8") as wf:
            subprocess.run([nm, "-n", app_elf], stdout=wf, text=True, check=False)
        with open(os.path.join(image_out, "application.asm"), "w", encoding="utf-8") as wf:
            subprocess.run([objdump, "-d", app_elf], stdout=wf, text=True, check=False)
    except Exception:
        pass

    if USE_TZ:
        axf_filename = "application.s.axf"
    else:
        axf_filename = "application.ntz.axf"
    shutil.copyfile(app_elf, os.path.join(image_out, axf_filename))

    # 可由環境覆寫 JSON / profile；預設走 FIRMWARE
    app_json   = os.environ.get("POSTBUILD_APP_JSON", sdk_amebapro2_application_path)
    app_profile= os.environ.get("POSTBUILD_FIRMWARE_PROFILE", "FIRMWARE")

    # application.bin
    out_img2 = os.path.join(build_dir, "application.bin")
    _run([sdk_elf2bin_path, "convert", app_json, app_profile, out_img2], cwd=image_out)

    # 如果 JSON 把檔生在 output/，幫你搬回來
    if not os.path.exists(out_img2):
        cands = glob.glob(os.path.join(image_out, "output", "application*.bin"))
        if cands:
            shutil.copy2(cands[0], out_img2)

    if not os.path.exists(out_img2):
        print(">>> WARN: application.bin not found after elf2bin convert（請檢查 JSON / profile / 路徑）")

    # 同步其他可能的副檔（非必需；imagetool 可能會用到）
    for name in ("application_image3_all.bin", "application_image3_psram.bin", "application_boot_all.bin"):
        p = os.path.join(image_out, name)
        if not os.path.exists(p):
            q = os.path.join(image_out, "output", name)
            if os.path.exists(q):
                shutil.copy2(q, p)

    # 對齊 CMake：複製到 output/
    outdir = os.path.join(image_out, "output")
    os.makedirs(outdir, exist_ok=True)
    for f in ("application.bin", axf_filename, "application.nm.map", "application.asm"):
        p = os.path.join(image_out, f)
        if os.path.exists(p):
            _safe_copy(p, os.path.join(outdir, f))

    print(">>> application (sdk_elf2bin_path) done")
    return {"application": out_img2 if os.path.exists(out_img2) else None}

def _post_bootloader_elf2bin_action(target, source, env):
    postprocess_bootloader_with_elf2bin()
    return 0

# 綁定 SCons target：把 application.elf 轉出 application.bin（與 CMake 對齊）
def _post_application_image_action(target, source, env):
    postprocess_application_with_elf2bin()
    return 0

bootloader_all_bin = env.Command(
    os.path.join(build_dir, "boot.bin"),  # 方便後面的 application 合併目標仍依此檔名
    bootloader_elf,
    _post_bootloader_elf2bin_action
)

# 生成 application 產物（image2 為必要；TZ=ON 才做 image3）
application_all_bin = env.Command(
    os.path.join(build_dir, "application.bin"),
    application_elf,
    _post_application_image_action
)

# =========================
# 完整合併程式（沿用你現有的 Python 版 imagetool）
# =========================
def _imagetool_image2_action(target, source, env):
    """
    Python 版 imagetool：對齊 SDK gnu_utility/image_tool/imagetool.sh 的主要步驟
    - 將 boot.bin + application.bin 依 4KB 對齊後合併
    - 如偵測到 image3（PSRAM/ALL），依「PSRAM 優先，其次 ALL」的順序追加
    - 安全性（RSIP / Secure Boot / RDP）由 hash/sign/sign_enc 三個 target 負責；此處僅產生最小可用的裸合併檔
    輸出檔名：
      flash_tz.bin  (TRUSTZONE=1)
      flash_ntz.bin (TRUSTZONE=0)
    """
    out_name = "flash_tz.bin" if USE_TZ else "flash_ntz.bin"
    out_path = os.path.join(build_dir, out_name)
    os.makedirs(build_dir, exist_ok=True)

    boot_bin = os.path.join(build_dir, "boot.bin")
    app_bin  = os.path.join(build_dir, "application.bin")

    if not os.path.exists(boot_bin):
        raise FileNotFoundError("boot.bin not found; bootloader postbuild failed?")
    if not os.path.exists(app_bin):
        raise FileNotFoundError("application.bin not found; application postbuild failed?")

    # 依 4KB 對齊：與工具鏈保持一致（flash 分區對齊）
    _pad_to_4k(boot_bin)
    _pad_to_4k(app_bin)

    # image3（有就追加；沒有就跳過）
    img3_candidates = [
        os.path.join(build_dir, "application_image3_psram.bin"),
        os.path.join(build_dir, "application_image3_all.bin"),
        os.path.join(build_dir, "application_boot_all.bin"),
    ]
    img3 = None
    for p in img3_candidates:
        if os.path.exists(p):
            img3 = p
            _pad_to_4k(img3)
            break

    parts = [boot_bin, app_bin] + ([img3] if img3 else [])
    _concat_bins(out_path, *parts)

    print(">>> imagetool: merged ->", out_path,
          "(+ image3:", os.path.basename(img3) if img3 else "none", ")")
    return 0

deps_for_merge = [bootloader_all_bin, application_all_bin]

bootloader_application_image2_bin = env.Command(
    os.path.join(build_dir, "flash_ntz.bin"),
    deps_for_merge,
    _imagetool_image2_action
)

# --- SCons targets / aliases 對齊 CMake 名稱 ---

sensor_iq_target = env.Command(
    [os.path.join(build_dir, "iq_set.bin"),
     os.path.join(build_dir, "isp_iq.bin"),
     os.path.join(build_dir, "firmware_isp_iq.bin")],
    [],  # 無顯式來源，純動作
    _sensor_iq_action
)

flash = env.Command(os.path.join(build_dir, ".stamp_plain_img"), [bootloader_application_image2_bin], _flash_action)

Alias("fcs_isp_iq", [sensor_iq_target])
Alias("flash",     [flash])

# --- Upload --- 
def _pick_flash_image():
    # 優先照旗標推導其實際檔名
    tgt = "flash_tz" if USE_TZ else "flash_ntz"
    if USE_WLANMP:
        tgt += "_mp"
    cand = os.path.join(build_dir, f"{tgt}.bin")
    if os.path.exists(cand):
        return cand
    # 後備：任選 build_dir 裡最新的 flash_*.bin
    cands = sorted(glob.glob(os.path.join(build_dir, "flash_*.bin")), key=os.path.getmtime, reverse=True)
    if cands:
        return cands[0]
    raise FileNotFoundError("no flash_*.bin found; build step didn't produce a flash image")

def upload_amebapro2(source, target, env):
    print(">>> Uploading AmebaPro2 image ...")
    port = env.GetProjectOption("upload_port") or os.environ.get("UPLOAD_PORT") or "COM3"
    baud = str(env.GetProjectOption("upload_speed") or os.environ.get("UPLOAD_SPEED") or 1500000)

    image = _pick_flash_image()
    print(f">>> Image: {image}")

    # Arduino core tools 來源路徑
    tool_dir_src = os.path.join(sdk_dir, "Arduino_package", "tools/Pro2_PG_tool _v1.4.3")
    if os.name == "nt":
        upload_tool = os.path.join(tool_dir_src, "uartfwburn.exe")
        flashloader_src = os.path.join(tool_dir_src, "flash_loader_nor.bin")
    else:
        upload_tool = os.path.join(tool_dir_src, "uartfwburn.linux")
        flashloader_src = os.path.join(tool_dir_src, "flash_loader_nor.bin")

    # 在 build_dir 下跑，讓程式能找到 flash_loader_nor.bin
    tool_dir = build_dir
    os.makedirs(tool_dir, exist_ok=True)
    flashloader_dst = os.path.join(tool_dir, "flash_loader_nor.bin")
    if not os.path.exists(flashloader_dst):
        shutil.copy(flashloader_src, flashloader_dst)
        print(f">>> Copied flashloader to {flashloader_dst}")

    # 以旗標模式呼叫；先試軟體進入下載模式（-d p2m），失敗再用手動模式
    attempts = [
        [upload_tool, "-p", port, "-b", baud, "-f", image, "-U", "-v", "pro2", "-r", "-d", "p2m"],
        [upload_tool, "-p", port, "-b", baud, "-f", image, "-U", "-v", "pro2", "-r"],
    ]
    for cmd in attempts:
        rc = _run(cmd, strict=False, cwd=tool_dir)
        if rc == 0:
            print(">>> Upload done!")
            return

    raise RuntimeError(
        "Upload failed. Hints: 1) 確認 platformio.ini 設定 upload_port=COMx；"
        "2) 若板子不支援軟體進入下載模式，請按住 UART/Download 鍵再 Reset；"
        "3) 若仍連不上，試把 upload_speed 降到 921600 或 115200。"
    )

# 🚩 Upload target (只負責上傳，不會在 build 時觸發)
upload_target = env.Alias("upload", flash, upload_amebapro2)
AlwaysBuild(upload_target) # 確保 pio run -t upload 會跑