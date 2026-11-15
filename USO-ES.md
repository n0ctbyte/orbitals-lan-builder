# Como usar el constructor

## Que necesitas

- Windows de 64 bits y Python 3.11 o superior, tambien de 64 bits.
- La carpeta `python` completa de este repositorio.
- Tu NUP original compatible de Orbitals Deluxe Edition 1.0.5.
- Unos 7 GB libres, mas margen. No necesitas un EXE ni una DLL de compresion.

No incluye el juego, claves, firmware ni Lichii. No cambia la ROM, partidas,
mandos, red o instalaciones del emulador. Es experimental y no oficial.

## Windows: generar el mod

1. Pulsa **Code → Download ZIP** en GitHub y extrae todo.
   Usa una ruta corta, por ejemplo `C:\OrbitalsBuilder`, tambien para las pruebas.
   Si rechaza una ruta demasiado larga, acortala; no cambies ajustes de Windows.
2. Abre PowerShell en la carpeta extraida. Comprueba `py -3 --version`:
   debe indicar Python 3.11 o superior. Si usas `python` en vez de `py -3`,
   sustituyelo en todos los comandos. No lo ejecutes como administrador.
3. Comprueba que Python sea de 64 bits:
   `py -3 -c "import struct; print(struct.calcsize('P') * 8)"` debe mostrar `64`.
4. Ejecuta estos comandos cambiando la ruta del original por la tuya:

```powershell
py -3 -B .\python\orbitals_lan_builder.py --check "D:\Games\Orbitals-original.nup"
py -3 -B .\python\orbitals_lan_builder.py --input "D:\Games\Orbitals-original.nup" --output "C:\Mods\Orbitals-LAN"
```

La primera orden solo comprueba el original en memoria. La segunda crea una
salida aparte. La carpeta de salida no debe existir ni estar dentro de la
biblioteca de juegos o del emulador. Espera a **Private mod created separately**.
Si rechaza la version, formato, checksum o ruta, no quites sus protecciones.
Renombrar NX/NSZ/NSP/XCI a NUP no convierte el archivo.

La salida ocupa unos 6,8 GB porque contiene recursos de tu copia del juego.
**No la publiques ni la subas a GitHub o VirusTotal.** Lo que se comparte aqui
es el constructor, no el mod generado.

## Windows, macOS o Linux: activarlo en Lichii

El constructor **solo funciona en Windows**. En macOS/Linux puedes copiar
privadamente la carpeta generada desde Windows; no hemos validado gameplay en
esos sistemas. No hay una orden nativa de generacion para ellos en esta version.

1. Usa un perfil separado de Lichii y conserva tus partidas originales.
2. Clic derecho sobre Orbitals → **Open Mod Data Location**.
3. Dentro de la salida generada, abre `040032B023CA4000`. Copia la carpeta
   **Minimal-Multiplayer** dentro de la ubicacion que te ha abierto Lichii.
   No copies otra carpeta de ID por encima.
4. En **Properties / Add-ons**, activa ese mod. No lo mezcles con otro mod que
   sustituya los mismos recursos del menu.
5. Reinicia Orbitals → **Multiplayer**. Deben aparecer **Create Game** y
   **Find Games**, sin casilla LAN. LAN queda activado por dentro.

Para quitarlo, desactivalo en Add-ons y reinicia. Tu NUP sigue intacto.

## Como jugar dos personas

Ambas necesitan versiones compatibles del juego, update, mod y emulador.

1. El anfitrion crea una room privada/con contrasena en Lichii, para dos.
2. La otra persona entra y ambas comprueban que aparecen en la misma room.
3. Arrancan Orbitals. Anfitrion: **Multiplayer → Create Game**.
   Invitado: **Multiplayer → Find Games**, elige la partida y entra.
4. Siguen las indicaciones de Ready/inicio del juego. Pueden ocultar el panel
   de la room, pero no pulsar **Leave Room** ni cerrar el emulador.

Ver una room en el listado no basta: el anfitrion tiene que ser accesible.
Por Internet puede hacer falta abrir su puerto UDP o usar una red privada
acordada entre ambas personas. Normalmente es UDP 24872, salvo que el anfitrion
haya elegido otro. El listado no es un servidor que retransmita la partida.
El constructor no configura puertos, firewall, VPN, Steam ni cuentas Nintendo.

## Las dos PR de Lichii

- [1593](https://github.com/zortos293/Lichii/pull/1593): devuelve correctamente
  IP/puerto numericos durante el establecimiento de sesion. Incorporada mediante
  la [1666](https://github.com/zortos293/Lichii/pull/1666).
- [1594](https://github.com/zortos293/Lichii/pull/1594): corrige los endpoints
  de sockets y la identidad IP virtual usada por las rooms ENet. Sigue abierta
  a 15/11/2026: no des por hecho que cualquier build publicada la incluye.

Hace falta un emulador que contenga ambos arreglos o equivalentes compatibles.
El mod cambia el menu; las PR arreglan el emulador. No son intercambiables.
No se ha certificado el juego entero, ni sesiones largas ni macOS/Linux.

El ZIP de fuentes de ejecucion dio **0/64 en VirusTotal**, no una garantia
absoluta. Detalles, limites y enlace al informe en [README](README.md).
