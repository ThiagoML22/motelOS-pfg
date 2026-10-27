-- Verifica las reglas del cierre de caja ciego en la base (RF-08, RF-09, RN-RES-02, RN-DER-03, RN-DER-04) y que
-- una habitacion tenga a lo sumo un turno en curso (RN-EXI-01).
-- Falla con error si alguna regla no se cumple. Corre dentro de una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_caja.sql
BEGIN;
DO $$
DECLARE
    op_a integer;
    op_b integer;
    op_b_admin integer;
    g14 integer;
    g22 integer;
    tid uuid;
    a RECORD;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.a', 'Conserje A', 'x', 'OPERADOR') RETURNING id INTO op_a;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.b', 'Conserje B', 'x', 'OPERADOR') RETURNING id INTO op_b;

    -- Guardia de las 14:00 de A, con un fondo de cambio de $5.000.
    INSERT INTO guardias (operador_id, franja, fondo_inicial) VALUES (op_a, '14:00', 5000) RETURNING id INTO g14;

    -- Una sola guardia abierta a la vez.
    bloqueado := false;
    BEGIN INSERT INTO guardias (operador_id, franja) VALUES (op_b, '22:00');
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se abrieron dos guardias a la vez'; END IF;

    -- RN-DER-04: un turno que abre A a las 21:30 ...
    INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (1, 1, 8000, 13000, 'En Curso', op_a, g14) RETURNING id INTO tid;

    -- RN-EXI-01: la misma habitacion no admite un segundo turno en curso (migracion 004).
    bloqueado := false;
    BEGIN INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                              operador_apertura_id, guardia_apertura_id)
          VALUES (1, 1, 8000, 8000, 'En Curso', op_a, g14);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se abrieron dos turnos en curso en la misma habitacion'; END IF;

    -- Un pago sin atribucion se rechaza (RNF-04).
    bloqueado := false;
    BEGIN INSERT INTO pagos (turno_id, monto, medio_pago) VALUES (tid, 1, 'EFECTIVO');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un pago sin operador ni guardia'; END IF;

    -- Un pago a nombre de otro operador se rechaza.
    bloqueado := false;
    BEGIN INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 1, 'EFECTIVO', op_b, g14);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un pago a nombre de un operador sin la guardia'; END IF;

    -- La guardia no se cierra sin arqueo.
    bloqueado := false;
    BEGIN UPDATE guardias SET estado = 'Cerrada', cerrada_en = CURRENT_TIMESTAMP WHERE id = g14;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cerro una guardia sin arqueo'; END IF;

    -- Solo el operador de la guardia confirma su arqueo.
    bloqueado := false;
    BEGIN INSERT INTO arqueos_caja (guardia_id, operador_id, declarado_efectivo, total_declarado, diferencia, categoria)
          VALUES (g14, op_b, 0, 0, 0, 'Correcto');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un operador ajeno confirmo el arqueo de la guardia'; END IF;

    -- A cierra su guardia a las 22:00 sin haber cobrado nada: la base calcula el sistema con el fondo
    -- ($5.000) aunque la aplicacion envie otros valores. A declara $5.000 en efectivo: Correcto.
    INSERT INTO arqueos_caja (guardia_id, operador_id, declarado_efectivo, total_declarado,
                              total_sistema, sistema_efectivo, diferencia, categoria)
    VALUES (g14, op_a, 5000, 5000, 99999, 99999, -94999, 'Faltante');
    SELECT * INTO a FROM arqueos_caja WHERE guardia_id = g14;
    IF a.total_sistema <> 5000 OR a.diferencia <> 0 OR a.categoria <> 'Correcto' THEN
        RAISE EXCEPTION 'La base no recalculo el arqueo: sistema %, diferencia %, categoria %',
            a.total_sistema, a.diferencia, a.categoria;
    END IF;
    UPDATE guardias SET estado = 'Cerrada', cerrada_en = CURRENT_TIMESTAMP WHERE id = g14;

    -- RN-RES-02: el arqueo confirmado no se modifica ni se borra.
    bloqueado := false;
    BEGIN UPDATE arqueos_caja SET declarado_efectivo = 1 WHERE guardia_id = g14;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'UPDATE sobre un arqueo confirmado no fue bloqueado'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM arqueos_caja WHERE guardia_id = g14;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'DELETE sobre un arqueo confirmado no fue bloqueado'; END IF;

    -- La guardia cerrada no se reabre ni se borra, y no recibe pagos.
    bloqueado := false;
    BEGIN UPDATE guardias SET estado = 'Abierta', cerrada_en = NULL WHERE id = g14;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se reabrio una guardia cerrada'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM guardias WHERE id = g14;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro una guardia'; END IF;

    bloqueado := false;
    BEGIN INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 13000, 'EFECTIVO', op_a, g14);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un pago a una guardia ya arqueada'; END IF;

    -- ... y lo cobra B a las 23:30, en la guardia de las 22:00: el pago entra a la caja de B.
    INSERT INTO guardias (operador_id, franja) VALUES (op_b, '22:00') RETURNING id INTO g22;
    INSERT INTO pagos (turno_id, monto, medio_pago, operador_id, guardia_id) VALUES (tid, 10000, 'EFECTIVO', op_b, g22);
    INSERT INTO pagos (turno_id, monto, medio_pago, comprobante_referencia, operador_id, guardia_id)
    VALUES (tid, 3000, 'POSNET', 'CUP-1', op_b, g22);
    UPDATE turnos SET estado = 'FINALIZADO', hora_fin = CURRENT_TIMESTAMP, operador_cierre_id = op_b WHERE id = tid;

    -- RF-09: B declara $10.000 en efectivo y $500 en POSNET; el sistema registra $13.000 -> Faltante de $2.500.
    INSERT INTO arqueos_caja (guardia_id, operador_id, declarado_efectivo, declarado_posnet, total_declarado,
                              diferencia, categoria)
    VALUES (g22, op_b, 10000, 500, 0, 0, 'Correcto');
    SELECT * INTO a FROM arqueos_caja WHERE guardia_id = g22;
    IF a.sistema_efectivo <> 10000 OR a.sistema_posnet <> 3000 OR a.total_sistema <> 13000
       OR a.total_declarado <> 10500 OR a.diferencia <> -2500 OR a.categoria <> 'Faltante' THEN
        RAISE EXCEPTION 'Arqueo de la guardia de las 22:00 mal calculado: %', row_to_json(a);
    END IF;

    -- El arqueo de A no incluye el cobro de B (RN-DER-04).
    SELECT * INTO a FROM arqueos_caja WHERE guardia_id = g14;
    IF a.total_sistema <> 5000 THEN
        RAISE EXCEPTION 'El cobro de las 23:30 entro a la guardia de las 14:00';
    END IF;

    -- Cierre supervisado (migracion 003): A deja su guardia abierta y se va.
    UPDATE guardias SET estado = 'Cerrada', cerrada_en = CURRENT_TIMESTAMP WHERE id = g22;
    INSERT INTO guardias (operador_id, franja) VALUES (op_a, '06:00') RETURNING id INTO g14;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.gerencia', 'Gerencia', 'x', 'ADMINISTRADOR') RETURNING id INTO op_b_admin;

    -- Otro conserje no puede confirmar el arqueo de A.
    bloqueado := false;
    BEGIN INSERT INTO arqueos_caja (guardia_id, operador_id, confirmado_por_id, observacion, declarado_efectivo,
                                    total_declarado, diferencia, categoria)
          VALUES (g14, op_a, op_b, 'Conserje A se retiro sin cerrar', 0, 0, 0, 'Correcto');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un conserje ajeno confirmo un cierre supervisado'; END IF;

    -- La gerencia sin observacion tampoco.
    bloqueado := false;
    BEGIN INSERT INTO arqueos_caja (guardia_id, operador_id, confirmado_por_id, declarado_efectivo,
                                    total_declarado, diferencia, categoria)
          VALUES (g14, op_a, op_b_admin, 0, 0, 0, 'Correcto');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un cierre supervisado sin observacion'; END IF;

    -- Con observacion, el arqueo queda en la caja de A y confirmado por la gerencia.
    INSERT INTO arqueos_caja (guardia_id, operador_id, confirmado_por_id, observacion, declarado_efectivo,
                              total_declarado, diferencia, categoria)
    VALUES (g14, op_a, op_b_admin, 'Conserje A se retiro sin cerrar su guardia', 0, 0, 0, 'Correcto');
    SELECT * INTO a FROM arqueos_caja WHERE guardia_id = g14;
    IF a.operador_id <> op_a OR a.confirmado_por_id <> op_b_admin OR a.categoria <> 'Correcto' THEN
        RAISE EXCEPTION 'Cierre supervisado mal registrado: %', row_to_json(a);
    END IF;

    -- Un arqueo comun registra a su propio operador como quien lo confirmo.
    SELECT * INTO a FROM arqueos_caja WHERE guardia_id = g22;
    IF a.confirmado_por_id IS DISTINCT FROM op_b THEN
        RAISE EXCEPTION 'El arqueo de la guardia de las 22:00 no registra quien lo confirmo';
    END IF;

    RAISE NOTICE 'Cierre de caja verificado: RN-RES-02, RN-DER-03, RN-DER-04 y cierre supervisado se cumplen en la base';
END $$;
ROLLBACK;
