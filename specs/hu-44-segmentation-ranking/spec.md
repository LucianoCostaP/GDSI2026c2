# Spec: HU-44, Ranking por pilar del puntaje

**Estimación:** 3 pts
**Prioridad:** Media
**MVP:** SÍ
**Épica:** Gestión de Eventos y Algoritmo de Scoring (Vista Admin)
**Depende de:** HU-25 (cálculo de rankings), HU-16 (desglose de componentes), HU-27 (fórmula base), HU-43 (padrón)

> Como Administrador
> Quiero que, al ejecutar el cálculo de rankings, se genere también un ranking por cada pilar del puntaje
> Para reconocer a los mejores según su tipo de participación

## Resumen

Cada corrida del cálculo produce, junto con el ranking general, tres rankings por pilar: **Asistencia**, **Participación institucional** y **Antigüedad y edad**. La pestaña «Calcular ranking» muestra el **top 10** de cada uno. Es una vista de solo lectura para el rol de gestión.

La estimación de 3 pts se apoya en que el módulo de scoring puro ya calcula los puntos por componente (HU-16). Esta historia reordena esos valores por pilar, los persiste junto a la corrida y los muestra, sin una fórmula nueva.

## Escenarios de usuario

### Escenario 1: Ver el top 10 por pilar tras un cálculo (P1)

El Administrador ejecuta el cálculo y, al completarse, consulta quiénes lideran cada tipo de participación.

**Aceptación**

1. **Dado** un cálculo completado, **cuando** el Administrador abre «Calcular ranking», **entonces** ve tres tablas con el top 10 de Asistencia, Participación institucional y Antigüedad y edad.
2. **Dado** esas tablas, **entonces** cada fila muestra posición, nombre, número de socio y puntos del pilar con dos decimales.
3. **Dado** esas tablas, **entonces** arriba se indican la versión de reglas y la fecha y hora del cálculo que las generó.

**Prueba independiente:** con un dataset de control (el mismo de HU-25), ejecutar el cálculo y verificar que cada tabla coincide con el orden esperado de su pilar.

### Escenario 2: Coherencia con el ranking general (P1)

**Aceptación**

1. **Dado** una ejecución del cálculo, **entonces** los tres rankings por pilar salen de la misma corrida que el general, con la misma versión de reglas y la misma fecha de corte.
2. **Dado** un socio, **entonces** sus puntos en cada pilar coinciden exactamente con los que muestra su desglose (HU-16).
3. **Dado** un socio con bonus de socio nuevo o con ajuste por tope, **entonces** ninguno de los dos forma parte de ningún ranking por pilar, y la suma de sus tres pilares puede no coincidir con su total (HU-14).

### Escenario 3: Empates y elegibilidad (P1)

**Aceptación**

1. **Dado** dos socios con los mismos puntos en un pilar, **entonces** se ordenan por antigüedad, luego por edad y luego por menor número de documento (criterio de HU-25).
2. **Dado** un socio con cuota vencida, **entonces** no aparece en ningún ranking por pilar. Su historial se conserva.

### Escenario 4: Estados del cálculo (P2)

**Aceptación**

1. **Dado** que nunca se ejecutó un cálculo, **entonces** se muestra «Todavía no hay un ranking calculado.» en lugar de tablas vacías.
2. **Dado** un cálculo en curso, **entonces** se siguen mostrando los datos del último completado, con la etiqueta «actualizando».
3. **Dado** un cálculo que falla, **entonces** se siguen mostrando los rankings del último cálculo completado, sin modificar.
4. **Dado** un cálculo que se completa, **entonces** los tres rankings se reemplazan junto con el general en una única operación atómica.

### Escenario 5: Pilares con pocos socios con puntos (P2)

**Aceptación**

1. **Dado** un pilar con menos de 10 socios con puntos, **entonces** se listan solo esos, sin filas vacías de relleno.
2. **Dado** un pilar sin ningún socio con puntos, **entonces** su tabla muestra un mensaje informativo y no una tabla vacía. *(Supuesto: el texto exacto se define en la implementación.)*

### Escenario 6: Acceso y privacidad (P1)

**Aceptación**

1. **Dado** un Administrador autenticado, **entonces** puede ver los rankings por pilar.
2. **Dado** un Socio autenticado, **entonces** no ve estos rankings en su portal, y el servidor rechaza el pedido si intenta consultarlos directamente.
3. **Dado** cualquier fila mostrada, **entonces** no incluye DNI ni email.
4. **Dado** la vista, **entonces** es de solo lectura: no hay controles para editar ni reordenar un puesto.

## Casos borde

- Un pilar con puntos en cero para todos: no hay ranking que mostrar para ese pilar.
- Un socio que ingresó después del último cálculo: no aparece hasta el próximo.
- Cambio de reglas publicado entre cálculos: las tablas siguen mostrando la versión de reglas con la que se calcularon, hasta el próximo cálculo.
- Dos Administradores consultando mientras corre un cálculo: ambos ven el último completado.
- Falla a mitad de la corrida: no puede quedar un ranking por pilar de una corrida y el general de otra (la atomicidad cubre los cuatro).

## Requisitos funcionales

- **FR-01:** Cada ejecución del cálculo (HU-25) DEBE generar, además del ranking general, tres rankings: Asistencia, Participación institucional y Antigüedad y edad.
- **FR-02:** El pilar Asistencia DEBE usar el término completo de la fórmula (frecuencia y distancia juntas), tal como pesa en el puntaje.
- **FR-03:** Cada ranking DEBE ordenar por los puntos del socio en ese pilar, con dos decimales, idénticos a los del desglose (HU-16).
- **FR-04:** Los cuatro rankings DEBEN salir de la misma corrida, con la misma versión de reglas y la misma fecha de corte.
- **FR-05:** El bonus de socio nuevo y el ajuste por tope NO DEBEN formar parte de ningún ranking por pilar.
- **FR-06:** Solo DEBEN participar los socios con la cuota al día.
- **FR-07:** Los empates DEBEN resolverse por antigüedad, luego edad y luego menor número de documento.
- **FR-08:** Los cuatro rankings DEBEN reemplazarse de forma atómica. Ante una falla o un cálculo en curso, DEBEN seguir mostrándose los del último cálculo completado.
- **FR-09:** La pantalla DEBE mostrar el top 10 de cada pilar, con posición, nombre, número de socio y puntos del pilar.
- **FR-10:** Si un pilar tiene menos de 10 socios con puntos, DEBE listar solo esos.
- **FR-11:** Sin ningún cálculo previo, DEBE mostrar «Todavía no hay un ranking calculado.».
- **FR-12:** DEBE indicar la versión de reglas y la fecha y hora del cálculo que generó las tablas.
- **FR-13:** Durante un cálculo en curso, DEBE mostrar el último completado con la etiqueta «actualizando».
- **FR-14:** La vista DEBE ser de solo lectura. NO DEBE existir ninguna operación para editar o reordenar un puesto.
- **FR-15:** Solo el rol de gestión DEBE acceder. El servidor DEBE rechazar el pedido de cualquier otro rol o de un usuario sin sesión.
- **FR-16:** La respuesta NO DEBE incluir DNI ni email (riesgo R10).
- **FR-17:** Cada corrida DEBE dejar auditado qué rankings por pilar generó y con qué versión de reglas.

## Entidades clave

- **Corrida de cálculo** (ya existe en HU-25): identifica la ejecución, su versión de reglas, su fecha de corte y su estado.
- **Ranking por pilar:** pertenece a una corrida y a un pilar (asistencia, participación institucional, antigüedad y edad). Contiene las posiciones ordenadas.
- **Posición en un pilar:** referencia al socio, sus puntos en el pilar y su puesto. No guarda DNI ni email, solo el vínculo al socio.
- **Registro de auditoría:** deja constancia de qué rankings por pilar generó cada corrida y con qué versión de reglas.

## Criterios de éxito

- **SC-01:** Para el dataset de control, los puntos de cada socio en cada pilar coinciden al 100 % con su desglose (HU-16).
- **SC-02:** Agregar los tres rankings no hace que la corrida de 500.000 socios supere el umbral de 15 minutos del riesgo R1.
- **SC-03:** Ningún rol distinto de gestión puede obtener los rankings por pilar, ni desde la interfaz ni consultando directamente.
- **SC-04:** Un cálculo interrumpido no deja nunca rankings de corridas distintas mezclados.

## Supuestos y puntos abiertos

- La historia **no cambia la fórmula ni sus pesos**: reutiliza los puntos por componente ya calculados.
- Los **tres pilares** son los que nombran HU-13 y HU-16. Frecuencia y distancia se muestran separadas en el desglose, pero acá cuentan como un solo pilar.
- El **top 10 es fijo**; no hay paginación ni exportación en esta historia.
- **Abierto:** el mensaje para un pilar sin ningún socio con puntos (Escenario 5.2) no está definido en los criterios. Conviene fijar el texto antes de implementar.
- **Abierto:** el desempate por antigüedad dentro del pilar «Antigüedad y edad» favorece al mismo grupo que ya domina ese pilar. Es coherente con HU-25, pero vale la pena confirmarlo.
