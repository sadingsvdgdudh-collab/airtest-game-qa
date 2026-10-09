import { Commander, PayloadData } from 'shardy';
import { T3Service } from '../T3Service';

/**
 * Make turn
 */
export const turn = (commander: Commander, payload: PayloadData, service: T3Service) => {
  const data = JSON.parse(payload.data.toString());
  service.makeTurn(data.g, data.p, data.x, data.y);
  commander.response(payload);
};
