-- Verifica (RNF-01, RNF-04, RNF-08, RN-RES-02) los permisos del rol de la aplicacion, motel_app:
-- no altera tablas ni deshabilita triggers, no borra pagos ni turnos, no crea operadores ni cambia
-- roles o claves, no reabre guardias, no modifica ni borra arqueos, y si elimina patentes.
-- Falla con error si alguna restriccion no se cumple. Corre dentro de una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_roles.sql  (como dueno)
BEGIN;
DO $$
DECLARE
    oid integer;
    gid integer;
    tid uuid;
    eliminadas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.roles', 'Verificacion', 'x', 'OPERADOR') RETURNING id INTO oid;
    INSERT INTO guardias (operador_id, franja) VALUES (oid, '06:00') RETURNING id INTO gid;
    INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (1, 1, 8000, 8000, 'En Curso', oid, gid) RETURNING id INTO tid;
    INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 8000, 'EFECTIVO', oid, gid);
    UPDATE turnos SET estado = 'FINALIZADO', hora_fin = CURRENT_TIMESTAMP, operador_cierre_id = oid WHERE id = tid;
    INSERT INTO estadias_activas (turno_id, identificador_vehicular) VALUES (tid, 'ZZ000ZZ');

    SET LOCAL ROLE motel_app;

    bloqueado := false;
    BEGIN ALTER TABLE turnos DISABLE TRIGGER trigger_check_turno_inmutable;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo deshabilitar un trigger de turnos'; END IF;

    bloqueado := false;
    BEGIN ALTER TABLE arqueos_caja DISABLE TRIGGER trigger_arqueo_inmutable;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo deshabilitar un trigger de arqueos'; END IF;

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

    -- RNF-04: la aplicacion no crea operadores ni cambia roles o claves (no puede escalar privilegios).
    bloqueado := false;
    BEGIN INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('intruso', 'X', 'x', 'ADMINISTRADOR');
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo crear un operador'; END IF;

    bloqueado := false;
    BEGIN UPDATE operadores SET rol = 'ADMINISTRADOR' WHERE id = oid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo cambiar el rol de un operador'; END IF;

    bloqueado := false;
    BEGIN UPDATE operadores SET hash_clave = 'y' WHERE id = oid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo cambiar la clave de un operador'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM operadores WHERE id = oid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar un operador'; END IF;

    -- Si puede registrar el resultado de un intento de acceso (bloqueo por intentos fallidos).
    UPDATE operadores SET intentos_fallidos = 1 WHERE id = oid;

    -- RN-RES-02: no modifica guardias fuera del cierre ni borra arqueos.
    bloqueado := false;
    BEGIN UPDATE guardias SET operador_id = oid, fondo_inicial = 999 WHERE id = gid;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo modificar los datos de apertura de una guardia'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM arqueos_caja;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar arqueos'; END IF;

    bloqueado := false;
    BEGIN UPDATE arqueos_caja SET diferencia = 0;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo modificar arqueos'; END IF;

    -- RNF-08: si elimina la patente de la estadia.
    DELETE FROM estadias_activas WHERE turno_id = tid;
    GET DIAGNOSTICS eliminadas = ROW_COUNT;
    IF eliminadas <> 1 THEN RAISE EXCEPTION 'motel_app no pudo eliminar la patente de la estadia (RNF-08)'; END IF;

    RESET ROLE;
    RAISE NOTICE 'Roles verificados: motel_app no altera tablas, triggers, operadores ni arqueos y si elimina patentes';
END $$;
ROLLBACK;
