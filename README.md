# formatos-traducciones
Software para llenar formatos traducidos facil y sencillamente.

======================================================================
DOCUMENTO MAESTRO DE CONTINUIDAD
PROYECTO: SOFTWARE DE FORMATOS TRADUCIDOS
======================================================================

PROPÓSITO DEL SISTEMA
----------------------------------------------------------------------
Desarrollar un sistema que permita crear, configurar y utilizar
formatos traducidos a partir de imágenes prediseñadas (templates).

El sistema utiliza una imagen previamente diseñada como base visual del
documento y permite definir qué información debe introducirse, mediante
qué preguntas se obtiene y exactamente cómo debe aparecer cada dato
sobre el template.

El proyecto está compuesto por dos aplicaciones principales:

1. APLICACIÓN CONFIGURADORA
2. APLICACIÓN DE CAPTURA Y LLENADO


======================================================================
1. APLICACIÓN CONFIGURADORA
======================================================================

La aplicación configuradora permite seleccionar una imagen prediseñada
que funcionará como TEMPLATE del formato.

Sobre ese template se define la estructura de información que deberá
contener el documento.

Para cada dato se puede establecer:

- identificador del campo;
- nombre del campo;
- pregunta que se presentará al usuario;
- orden de la pregunta;
- tipo de dato;
- obligatoriedad;
- posición;
- área disponible;
- tipografía;
- tamaño del texto;
- estilo;
- alineación;
- color;
- propiedades necesarias para su renderizado.

La aplicación configuradora debe permitir visualizar el template y
establecer gráficamente dónde será colocado cada dato.

La configuración deberá poder guardarse para utilizar posteriormente
ese mismo formato.


======================================================================
2. TEMPLATE
======================================================================

El template es la imagen prediseñada que contiene el diseño gráfico del
formato.

El template constituye la base visual del documento.

El sistema agrega sobre esa imagen los textos correspondientes a los
datos capturados.

El diseño gráfico del template debe conservarse.

Los elementos visuales ya existentes en el template permanecen como
parte del documento final.


======================================================================
3. CONFIGURACIÓN DEL FORMATO
======================================================================

La configuración funciona como las instrucciones que indican al sistema
cómo llenar un determinado template.

Debe establecer:

- qué información se solicita;
- en qué orden se solicita;
- qué pregunta se muestra;
- dónde aparece cada respuesta;
- cómo se renderiza cada respuesta.

Conceptualmente:

TEMPLATE
    +
CONFIGURACIÓN
    =
FORMATO PREPARADO PARA SER LLENADO


======================================================================
4. APLICACIÓN DE CAPTURA Y LLENADO
======================================================================

La segunda aplicación utiliza una configuración previamente creada.

Su función es realizar preguntas consecutivas al usuario.

Ejemplo:

Pregunta 1
¿Cuál es el nombre completo?

Respuesta:
JUAN PÉREZ GARCÍA

Pregunta 2
¿Cuál es la fecha de nacimiento?

Respuesta:
15/08/1990

Pregunta 3
¿Cuál es el lugar de nacimiento?

Respuesta:
MEXICALI


El proceso continúa hasta completar todos los datos necesarios.


======================================================================
5. FLUJO DE CAPTURA
======================================================================

CONFIGURACIÓN
      ↓
CARGAR FORMATO
      ↓
PREGUNTA
      ↓
RESPUESTA
      ↓
SIGUIENTE PREGUNTA
      ↓
RESPUESTA
      ↓
SIGUIENTE PREGUNTA
      ↓
...
      ↓
FINALIZAR CAPTURA
      ↓
VALIDAR DATOS
      ↓
RENDERIZAR
      ↓
EXPORTAR


======================================================================
6. CAMPOS
======================================================================

Cada información que deba introducirse constituye un CAMPO.

Ejemplo:

ID:
nombre_completo

Pregunta:
¿Cuál es el nombre completo?

Respuesta:
JUAN PÉREZ GARCÍA


El ID permite mantener identificada la información dentro del sistema.


======================================================================
7. PREGUNTAS
======================================================================

Las preguntas son definidas previamente durante la configuración del
formato.

La aplicación de captura solamente las presenta siguiendo el orden
establecido.

Las preguntas deben ser consecutivas y mantener la información
introducida durante todo el proceso.


======================================================================
8. CONSERVACIÓN DE RESPUESTAS
======================================================================

Las respuestas introducidas deben permanecer disponibles mientras se
está llenando el documento.

Al avanzar y retroceder entre preguntas, los datos ya introducidos no
deben perderse.

Si el usuario modifica una respuesta, debe actualizarse el dato
correspondiente.


======================================================================
9. DATOS VACÍOS
======================================================================

Cuando un dato sea opcional y el usuario lo deje vacío, el campo debe
permanecer vacío.

No deben introducirse automáticamente textos sustitutos.

El sistema no debe inventar información.


======================================================================
10. VALIDACIÓN
======================================================================

Los campos que tengan reglas de validación deberán comprobarse antes
del renderizado final.

Cuando una respuesta no cumpla una regla establecida, el sistema deberá
informar el problema y permitir corregirlo.


======================================================================
11. RENDERIZADO
======================================================================

Una vez obtenidas y validadas las respuestas, el sistema debe realizar
el renderizado.

El Renderer recibe:

- template;
- configuración;
- datos.

Y produce:

- imagen final.


======================================================================
12. COLOCACIÓN DEL TEXTO
======================================================================

Cada respuesta debe aparecer en la posición establecida durante la
configuración.

La aplicación de captura no debe solicitar al usuario que indique
manualmente dónde colocar cada dato.

Esa información pertenece a la configuración del formato.


======================================================================
13. FORMATO DEL TEXTO
======================================================================

Las propiedades visuales definidas para cada campo deben aplicarse
durante el renderizado.

Entre ellas pueden encontrarse:

- fuente;
- tamaño;
- estilo;
- alineación;
- color;
- posición;
- área;
- demás propiedades necesarias.


======================================================================
14. DIMENSIONES DEL RESULTADO
======================================================================

REGLA FUNDAMENTAL:

El resultado debe tener exactamente las mismas dimensiones en píxeles
que el template utilizado.

El sistema NO debe imponer una dimensión universal.

Ejemplo:

Template:
1650 × 2550 px

Resultado:
1650 × 2550 px


Otro template:

2480 × 3508 px

Resultado:
2480 × 3508 px


El tamaño de salida depende del template utilizado.


======================================================================
15. RESOLUCIÓN
======================================================================

La imagen final debe conservar:

300 PPP


Ejemplo:

Template:
1650 × 2550 px
300 PPP

Resultado:
1650 × 2550 px
300 PPP


======================================================================
16. MODO DE COLOR
======================================================================

La salida debe ser:

RGB


La exportación no debe solicitar al usuario seleccionar entre diferentes
modos de color.

El formato de salida establecido para el proyecto es RGB.


======================================================================
17. MEJORAMIENTO DE IMAGEN
======================================================================

No se requiere procesamiento de mejoramiento de imagen.

El template ya es un recurso gráfico preparado previamente.

El sistema debe concentrarse en:

- capturar información;
- posicionarla;
- darle el formato configurado;
- renderizarla;
- exportarla.


======================================================================
18. EXPORTACIÓN
======================================================================

La imagen final debe exportarse como:

JPEG

con:

- calidad 100 %;
- RGB;
- 300 PPP;
- mismo ancho del template;
- mismo alto del template.


======================================================================
19. RESULTADO FINAL
======================================================================

El resultado final es:

TEMPLATE ORIGINAL
+
TEXTOS RENDERIZADOS
=
FORMATO TRADUCIDO TERMINADO


La imagen resultante mantiene el tamaño original del template.


======================================================================
20. VERIFICACIÓN
======================================================================

Después de generar la imagen se debe comprobar:

- archivo generado;
- formato JPEG;
- RGB;
- 300 PPP;
- calidad 100 %;
- ancho;
- alto;
- correcta colocación de los textos.


======================================================================
21. PROTECCIÓN DEL TEMPLATE
======================================================================

El archivo template original debe permanecer sin modificaciones.

La imagen generada debe ser un archivo independiente.


======================================================================
22. PRINCIPIO DE DESARROLLO
======================================================================

El desarrollo debe realizarse sobre la estructura existente.

Cuando una función ya funciona correctamente, debe conservarse.

Las modificaciones deben limitarse a lo necesario para:

- corregir errores;
- implementar funciones pendientes;
- integrar funciones;
- cumplir las especificaciones establecidas.


======================================================================
23. MÉTODO DE CORRECCIÓN DEL CÓDIGO
======================================================================

Cuando se encuentre un problema se deberá explicar:

1. Cuál es la falla.
2. Qué hacía el código anterior.
3. Por qué producía el problema.
4. Qué se modifica.
5. Qué hace la nueva implementación.
6. Cómo se verificó.

Cuando se modifique un archivo de código se deberá entregar el archivo
completo corregido.


======================================================================
24. ESTADO DEL PROYECTO
======================================================================

Los bloques 1A–1Z
2A–2Z
3A–3Z
4A–4Z

constituyen las etapas anteriores de definición y desarrollo del
proyecto.

El siguiente punto de continuidad es:

BLOQUE 5


======================================================================
25. BLOQUE 5
======================================================================

El Bloque 5 debe comenzar con una revisión técnica del proyecto real.

PRIMER OBJETIVO:

Identificar exactamente cómo está implementado actualmente el sistema.

Se revisará:

- estructura de archivos;
- aplicaciones;
- módulos;
- templates;
- archivos de configuración;
- sistema de campos;
- sistema de preguntas;
- almacenamiento de respuestas;
- Renderer;
- exportador.


======================================================================
26. SECUENCIA DE TRABAJO DEL BLOQUE 5
======================================================================

5A
Inventario técnico del proyecto.

5B
Revisión de la aplicación configuradora.

5C
Revisión de la estructura de configuración.

5D
Revisión de la aplicación de captura.

5E
Revisión del sistema de preguntas.

5F
Revisión de conservación de datos.

5G
Revisión de validaciones.

5H
Revisión del Renderer.

5I
Revisión del posicionamiento de textos.

5J
Revisión de tipografías.

5K
Revisión de exportación.

5L
Verificación JPEG/RGB/300 PPP/100 %.

5M
Verificación de dimensiones idénticas al template.

5N
Pruebas integrales.

5O
Pruebas de regresión.

5P
Correcciones necesarias.

5Q
Versión candidata.

5R
Pruebas finales.

5S
Versión final.

5T
Documentación técnica.

5U
Preparación del paquete final.


======================================================================
27. FLUJO COMPLETO DEL SISTEMA
======================================================================

                 TEMPLATE
                    ↓
          APLICACIÓN CONFIGURADORA
                    ↓
              DEFINICIÓN DE
                 CAMPOS
                    ↓
              DEFINICIÓN DE
                PREGUNTAS
                    ↓
              DEFINICIÓN DE
                POSICIONES
                    ↓
              DEFINICIÓN DE
              PROPIEDADES DE
                  TEXTO
                    ↓
            GUARDAR CONFIGURACIÓN
                    ↓
          APLICACIÓN DE CAPTURA
                    ↓
            PREGUNTAS CONSECUTIVAS
                    ↓
                RESPUESTAS
                    ↓
                VALIDACIÓN
                    ↓
                RENDERIZADO
                    ↓
             TEMPLATE + TEXTOS
                    ↓
                 JPEG RGB
                    ↓
                300 PPP
                    ↓
              CALIDAD 100 %
                    ↓
       MISMAS DIMENSIONES DEL TEMPLATE
                    ↓
               VERIFICACIÓN
                    ↓
             FORMATO TERMINADO


======================================================================
28. OBJETIVO FINAL DEL PROYECTO
======================================================================

Crear un sistema práctico mediante el cual sea posible preparar
previamente distintos formatos traducidos utilizando templates
gráficos y posteriormente llenarlos de manera rápida mediante una
secuencia de preguntas.

El usuario no necesita editar manualmente el diseño del documento.

La aplicación se encarga de:

- preguntar;
- recibir;
- conservar;
- validar;
- posicionar;
- formatear;
- renderizar;
- exportar.

El resultado es una imagen terminada del formato correspondiente.


======================================================================
29. REGLAS FUNDAMENTALES
======================================================================

1. El template define el tamaño de la imagen final.

2. El resultado conserva exactamente las dimensiones del template.

3. El resultado es RGB.

4. El resultado es JPEG.

5. La calidad JPEG es 100 %.

6. La resolución es 300 PPP.

7. Los datos son obtenidos mediante preguntas consecutivas.

8. La configuración determina dónde y cómo aparece cada dato.

9. Las respuestas deben conservarse durante la captura.

10. Los campos opcionales pueden permanecer vacíos.

11. No se deben inventar datos.

12. El template original no se modifica.

13. No se debe aplicar mejoramiento de imagen.

14. No se debe redimensionar arbitrariamente el template.

15. No se debe deformar el template.

16. El código existente que funcione debe conservarse.

17. Las modificaciones deben realizarse únicamente cuando sean
    necesarias.

18. Todo cambio debe comprobarse antes de considerarlo terminado.
