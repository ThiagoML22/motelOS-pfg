-- Verifica (RN-RES-01) que el esquema bloquea UPDATE y DELETE sobre turnos finalizados, sus pagos y sus
-- consumos. Falla con error si alguna operacion no es bloqueada. Corre dentro de una transaccion que se
-- revierte: no deja datos en la base.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_inmutabilidad.sql
BEGIN;
DO $$
DECLARE
    oid integer;
    gid integer;
    tid uuid;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.inmutable', 'Verificacion', 'x', 'OPERADOR') RETURNING id INTO oid;
    INSERT INTO guardias (operador_id, franja) VALUES (oid, '14:00') RETURNING id INTO gid;

    INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (1, 1, 8000, 8800, 'En Curso', oid, gid) RETURNING id INTO tid;
    INSERT INTO detalles_consumo (turno_id, articulo_id, cantidad, precio_unitario, subtotal, operador_id)
    VALUES (tid, 1, 1, 800, 800, oid);
    INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 8800, 'EFECTIVO', oid, gid);
    UPDATE turnos SET estado = 'FINALIZADO', hora_fin = CURRENT_TIMESTAMP, operador_cierre_id = oid WHERE id = tid;

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

    bloqueado := false;
    BEGIN INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 1, 'EFECTIVO', oid, gid);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un pago sobre un turno finalizado'; END IF;

    RAISE NOTICE 'RN-RES-01 verificada: los registros de turnos finalizados son inmutables';
END $$;
ROLLBACK;
