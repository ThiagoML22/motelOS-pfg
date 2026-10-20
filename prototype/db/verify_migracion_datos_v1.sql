-- Carga datos con la forma de la v1.2 (sin operadores ni guardias) en una base que solo tiene la
-- migracion 001. Despues se aplica 002 y se comprueba que la historia queda intacta y que lo nuevo
-- exige atribucion. Lo usa el canal en una base descartable.
-- Paso 1 (antes de 002): psql -v fase=antes -f db/verify_migracion_datos_v1.sql
-- Paso 2 (despues de 002): psql -v fase=despues -f db/verify_migracion_datos_v1.sql
\if :{?fase}
\else
\set fase antes
\endif
SELECT :'fase' = 'antes' AS es_antes \gset
\if :es_antes
INSERT INTO turnos (id, habitacion_id, tarifa_id, tarifa_base, total_general, estado, hora_fin)
VALUES ('00000000-0000-0000-0000-0000000000a1', 1, 1, 8000, 8800, 'FINALIZADO', CURRENT_TIMESTAMP);
INSERT INTO pagos (turno_id, monto, medio_pago)
VALUES ('00000000-0000-0000-0000-0000000000a1', 8800, 'EFECTIVO');
INSERT INTO detalles_consumo (turno_id, articulo_id, cantidad, precio_unitario, subtotal)
VALUES ('00000000-0000-0000-0000-0000000000a1', 1, 1, 800, 800);
\else
DO $$
DECLARE
    n integer;
    bloqueado boolean := false;
BEGIN
    SELECT count(*) INTO n FROM pagos
     WHERE turno_id = '00000000-0000-0000-0000-0000000000a1' AND monto = 8800 AND guardia_id IS NULL;
    IF n <> 1 THEN RAISE EXCEPTION 'La migracion 002 altero los pagos de la v1'; END IF;

    BEGIN
        INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado)
        VALUES (2, 1, 8000, 8000, 'En Curso');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Despues de 002 se abrio un turno sin operador'; END IF;
    RAISE NOTICE 'Migracion desde v1.2 verificada: historia intacta y atribucion exigida para lo nuevo';
END $$;
\endif
