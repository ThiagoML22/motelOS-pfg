-- Verifica (RNF-01 / RNF-08) que el rol de la aplicacion, motel_app, no puede alterar las tablas ni
-- deshabilitar triggers, no puede modificar ni borrar pagos y turnos cerrados, y si puede eliminar patentes.
-- Falla con error si alguna restriccion no se cumple.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con init.sql aplicado> -f db/verify_roles.sql  (como dueno de las tablas)
DO $$
DECLARE
    tid uuid;
    eliminadas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado)
    VALUES (1, 1, 8000, 8000, 'FINALIZADO') RETURNING id INTO tid;
    INSERT INTO pagos (turno_id, monto, medio_pago) VALUES (tid, 100, 'EFECTIVO');
    INSERT INTO estadias_activas (turno_id, identificador_vehicular) VALUES (tid, 'ZZ000ZZ');

    SET LOCAL ROLE motel_app;

    bloqueado := false;
    BEGIN ALTER TABLE turnos DISABLE TRIGGER trigger_check_turno_inmutable;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo deshabilitar un trigger de turnos'; END IF;

    bloqueado := false;
    BEGIN ALTER TABLE turnos DROP COLUMN total_general;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo alterar la estructura de turnos'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM pagos WHERE turno_id = tid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar pagos'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM turnos WHERE id = tid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar un turno'; END IF;

    DELETE FROM estadias_activas WHERE turno_id = tid;
    GET DIAGNOSTICS eliminadas = ROW_COUNT;
    IF eliminadas <> 1 THEN RAISE EXCEPTION 'motel_app no pudo eliminar la patente de la estadia (RNF-08)'; END IF;

    RESET ROLE;
    RAISE NOTICE 'Roles verificados: motel_app no altera tablas ni triggers y si elimina patentes';
END $$;
