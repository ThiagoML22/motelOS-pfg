-- db/migraciones/004_un_turno_por_habitacion.sql
-- Una habitacion tiene a lo sumo un turno En Curso (RN-EXI-01). La aplicacion ya rechaza abrir un turno sobre
-- una habitacion que no esta Libre, pero consulta y confirma en dos pasos: dos aperturas simultaneas podian
-- ver la habitacion Libre y abrir dos turnos. La regla queda en la base, que es la autoridad de escritura.
-- El indice es parcial para conservar el historial: una habitacion tiene muchos turnos finalizados y como
-- maximo uno en curso.
-- Se aplica con el usuario dueno de las tablas, despues de 003_cierre_supervisado.sql.

CREATE UNIQUE INDEX turnos_uno_en_curso_por_habitacion ON turnos (habitacion_id) WHERE estado = 'En Curso';
