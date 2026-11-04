-- Verifica la migracion 016 con el rol de la aplicacion, motel_app: un turno cambia de habitacion solo con su traslado, los
-- hechos quedan a nombre de la sesion y en su guardia abierta, un arreglo se resuelve una vez, despues solo cambia el costo,
-- nada se borra, y cada establecimiento ve solo lo suyo. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_operacion.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje integer;
    ajeno integer;
    categoria integer;
    tarifa integer;
    habitacion integer;
    habitacion_dos integer;
    guardia integer;
    guardia_ajena integer;
    turno uuid;
    arreglo integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-op', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.o', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.o2', 'Otro', 'x', 'OPERADOR')
    RETURNING id INTO ajeno;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif operacion') RETURNING id INTO categoria;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif operacion', 8000, 120, 0, 30, 2500, true, categoria) RETURNING id INTO tarifa;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9941, 'Ocupada', categoria) RETURNING id INTO habitacion;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9942, 'Libre', categoria) RETURNING id INTO habitacion_dos;
    INSERT INTO guardias (operador_id, franja, estado, cerrada_en) VALUES (ajeno, '22:00', 'Cerrada', now())
    RETURNING id INTO guardia_ajena;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Un turno no cambia de habitacion sin su traslado.
    bloqueado := false;
    BEGIN UPDATE turnos SET habitacion_id = habitacion_dos WHERE id = turno;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un turno cambio de habitacion sin traslado'; END IF;

    -- 2. El traslado es a nombre de la sesion y en su guardia abierta.
    bloqueado := false;
    BEGIN INSERT INTO traslados_turno (turno_id, desde_habitacion_id, hacia_habitacion_id, motivo, operador_id, guardia_id)
    VALUES (turno, habitacion, habitacion_dos, 'CLIENTE', ajeno, guardia);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se traslado a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO traslados_turno (turno_id, desde_habitacion_id, hacia_habitacion_id, motivo, operador_id, guardia_id)
    VALUES (turno, habitacion, habitacion_dos, 'CLIENTE', conserje, guardia_ajena);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se traslado en una guardia cerrada y ajena'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO traslados_turno (turno_id, desde_habitacion_id, hacia_habitacion_id, motivo, operador_id, guardia_id)
    VALUES (turno, habitacion, habitacion, 'CLIENTE', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se traslado a la misma habitacion'; END IF;

    -- 3. Con su traslado, cambia; y el traslado no se toca.
    INSERT INTO traslados_turno (turno_id, desde_habitacion_id, hacia_habitacion_id, motivo, operador_id, guardia_id)
    VALUES (turno, habitacion, habitacion_dos, 'FALLA', conserje, guardia);
    UPDATE turnos SET habitacion_id = habitacion_dos WHERE id = turno;
    bloqueado := false;
    BEGIN UPDATE traslados_turno SET motivo = 'OTRO' WHERE turno_id = turno;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio un traslado'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM traslados_turno WHERE turno_id = turno;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un traslado'; END IF;

    -- 4. Un arreglo se abre a nombre de la sesion y empieza abierto.
    bloqueado := false;
    BEGIN INSERT INTO arreglos (habitacion_id, tipo, rubro, descripcion, abierto_por_id)
    VALUES (habitacion, 'FALLA', 'AIRE', 'No enfria', ajeno);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se abrio un arreglo a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO arreglos (habitacion_id, tipo, rubro, descripcion, abierto_por_id)
    VALUES (habitacion, 'FALLA', 'AIRE', '   ', conserje);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un arreglo sin descripcion'; END IF;
    INSERT INTO arreglos (habitacion_id, tipo, rubro, descripcion, abierto_por_id)
    VALUES (habitacion, 'FALLA', 'AIRE', 'No enfria', conserje) RETURNING id INTO arreglo;

    -- 5. Lo reportado no cambia.
    bloqueado := false;
    BEGIN UPDATE arreglos SET descripcion = 'Otra cosa' WHERE id = arreglo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio lo reportado'; END IF;

    -- 6. Resolverlo pide quien lo reparo y queda a nombre de la sesion.
    bloqueado := false;
    BEGIN UPDATE arreglos SET estado = 'Resuelto', resuelto_por_id = conserje, resuelto_en = now() WHERE id = arreglo;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se resolvio sin decir quien lo reparo'; END IF;
    bloqueado := false;
    BEGIN UPDATE arreglos SET estado = 'Resuelto', resuelto_por_id = ajeno, resuelto_en = now(), reparado_por = 'Tecnico'
          WHERE id = arreglo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se resolvio a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN UPDATE arreglos SET costo = -1 WHERE id = arreglo;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un costo negativo'; END IF;
    UPDATE arreglos SET estado = 'En curso' WHERE id = arreglo;
    bloqueado := false;
    BEGIN UPDATE arreglos SET estado = 'Abierto' WHERE id = arreglo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un arreglo volvio atras'; END IF;
    UPDATE arreglos SET estado = 'Resuelto', resuelto_por_id = conserje, resuelto_en = now(), reparado_por = 'Tecnico'
    WHERE id = arreglo;

    -- 7. Una vez resuelto, solo cambia el costo; y no se borra.
    UPDATE arreglos SET costo = 15000 WHERE id = arreglo;
    bloqueado := false;
    BEGIN UPDATE arreglos SET reparado_por = 'Otro' WHERE id = arreglo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio quien lo reparo'; END IF;
    bloqueado := false;
    BEGIN UPDATE arreglos SET estado = 'En curso' WHERE id = arreglo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se reabrio un arreglo resuelto'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM arreglos WHERE id = arreglo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un arreglo'; END IF;

    -- 8. Un recuento por prenda y momento, sin negativos, en la guardia propia e inmutable.
    INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia, conserje, 'CIERRE', 'TOALLAS', 40, 10, 16);
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia, conserje, 'CIERRE', 'TOALLAS', 41, 10, 16);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entraron dos recuentos del mismo momento'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia, conserje, 'APERTURA', 'SABANAS', -1, 0, 0);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un recuento negativo'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia_ajena, ajeno, 'CIERRE', 'SABANAS', 1, 0, 0);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se conto a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN UPDATE ropa_conteos SET limpias = 99 WHERE guardia_id = guardia;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio un recuento'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM ropa_conteos WHERE guardia_id = guardia;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un recuento'; END IF;

    -- 9. Los movimientos de ropa, igual.
    INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad)
    VALUES (guardia, conserje, 'SABANAS', 'LAVANDERIA_SALE', 12);
    bloqueado := false;
    BEGIN INSERT INTO ropa_movimientos (guardia_id, operador_id, prenda, tipo, cantidad)
    VALUES (guardia, conserje, 'SABANAS', 'COMPRA', 0);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un movimiento sin cantidad'; END IF;
    bloqueado := false;
    BEGIN UPDATE ropa_movimientos SET cantidad = 1 WHERE guardia_id = guardia;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio un movimiento'; END IF;

    -- 10. Un traspaso por guardia, que no cambia.
    INSERT INTO traspasos (guardia_saliente_id, guardia_id, operador_id, resumen)
    VALUES (guardia_ajena, guardia, conserje, '{"turnos": []}');
    bloqueado := false;
    BEGIN INSERT INTO traspasos (guardia_id, operador_id, resumen) VALUES (guardia, conserje, '{}');
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entraron dos traspasos para una guardia'; END IF;
    bloqueado := false;
    BEGIN UPDATE traspasos SET resumen = '{}' WHERE guardia_id = guardia;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio un traspaso'; END IF;

    -- 11. Otro establecimiento no ve nada de esto.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT (SELECT count(*) FROM arreglos) + (SELECT count(*) FROM ropa_conteos) + (SELECT count(*) FROM ropa_movimientos)
         + (SELECT count(*) FROM traspasos) + (SELECT count(*) FROM traslados_turno) INTO filas;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio la operacion de otro'; END IF;
    RAISE NOTICE 'verify_operacion: traslados, arreglos, recuentos, movimientos, traspasos y aislamiento verificados';
END $$;
ROLLBACK;
