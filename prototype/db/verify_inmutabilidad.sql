-- Verifica (RN-RES-01) que el esquema de init.sql bloquea UPDATE y DELETE sobre turnos
-- finalizados, sus pagos y sus consumos. Falla con error si alguna operacion no es bloqueada.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con init.sql aplicado> -f db/verify_inmutabilidad.sql
DO $$
DECLARE
    tid uuid;
    bloqueado boolean;
BEGIN
    INSERT INTO turnos (habitacion_id, estado) VALUES (1, 'FINALIZADO') RETURNING id INTO tid;
    INSERT INTO pagos (turno_id, monto, medio_pago) VALUES (tid, 100, 'EFECTIVO');
    INSERT INTO detalles_consumo (turno_id, articulo_id, cantidad, precio_unitario, subtotal)
    VALUES (tid, 1, 1, 800, 800);

    bloqueado := false;
    BEGIN UPDATE turnos SET total_general = 1 WHERE id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'UPDATE sobre turnos finalizados no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM turnos WHERE id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'DELETE sobre turnos finalizados no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN UPDATE pagos SET monto = 1 WHERE turno_id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'UPDATE sobre pagos no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM pagos WHERE turno_id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'DELETE sobre pagos no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN UPDATE detalles_consumo SET cantidad = 9 WHERE turno_id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'UPDATE sobre consumos de un turno finalizado no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM detalles_consumo WHERE turno_id = tid;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'DELETE sobre consumos de un turno finalizado no fue bloqueado'; END IF;

    RAISE NOTICE 'RN-RES-01 verificada: los registros de turnos finalizados son inmutables';
END $$;
