import { Commander, PayloadData } from 'shardy';
import { T3Service } from '../T3Service';

/**
 * Exit from game
 */
export const exit = (commander: Commander, payload: PayloadData, service: T3Service) => {
  const data = JSON.parse(payload.data.toString());
  service.exitGame(data.g, data.p);
  commander.response(payload);
};
